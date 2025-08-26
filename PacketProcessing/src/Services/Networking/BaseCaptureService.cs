namespace PacketProcessing.Services.Networking;

using System.Collections.Concurrent;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using SharpPcap;
using SharpPcap.LibPcap;
using System.Threading.Channels;
using Microsoft.Extensions.Configuration;
using PacketProcessing.Entities;

public abstract class BaseCaptureService<T> : BackgroundService where T : BasePacketEntity
{
    protected ILogger<BaseCaptureService<T>> _logger;  
    protected string _protocol;
    protected IReadOnlyList<string> _ips;
    protected ConcurrentDictionary<string, LibPcapLiveDevice> _activeDevices;
    protected Channel<T> _channel; 
    protected Func<ReadOnlyMemory<byte>, T> PacketParser { get; set; }
    protected Func<T, Task> PacketHandler { get; set; }
    protected bool _isCapturing = false;
    protected readonly object _captureLock = new object();

    public BaseCaptureService(
        ILogger<BaseCaptureService<T>> logger,
        IConfiguration configurationManager,
        string dataPipeName,
        ConcurrentDictionary<string, LibPcapLiveDevice> activeDevices)
    {
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _activeDevices = activeDevices ?? throw new ArgumentNullException(nameof(activeDevices));
        
        // Get configuration for this specific DataPipe
        var dataPipeSection = configurationManager.GetSection("DataPipes").GetSection(dataPipeName);
        var channelSection = dataPipeSection.GetSection("Channel");
        var networkSection = dataPipeSection.GetSection("Network");
        
        // Get channel configuration
        var maxMembers = channelSection.GetValue<int>("Members");
        
        // Get network configuration
        _protocol = networkSection.GetValue<string>("Protocol") ?? "tcp";
        _ips = networkSection.GetSection("IPs").Get<string[]>() ?? new string[0];
        
        _logger.LogInformation("Initializing {DataPipeName} with protocol: {Protocol}, IPs: {IPs}, MaxChannelMembers: {MaxMembers}", 
            dataPipeName, _protocol, string.Join(", ", _ips), maxMembers);
        
        // Create bounded channel with max members from configuration
        _channel = Channel.CreateBounded<T>(new BoundedChannelOptions(maxMembers)
        {
            SingleWriter = false,
            SingleReader = true,
        });
    }
    
    protected virtual string GenerateFilter()
    {
        var ipExpr = string.Join(" or ", _ips.Select(ip => $"host {ip}")); // Generate a filter for the given IPs as "192.168.1.1 or 192.168.1.2"

        return $"{_protocol} and ({ipExpr})";// Final output is "tcp and (host 192.168.1.1 or host 192.168.1.2)"
    }

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        try
        {
            _logger.LogInformation("Capture service initialized. Waiting for start signal...");

            // Wait for cancellation (application shutdown) without starting capture
            while (!ct.IsCancellationRequested)
            {
                await Task.Delay(1000, ct);
            }
        }
        catch (OperationCanceledException) { /* normal on shutdown */ }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error in packet capture service");
        }
    }

    private async Task StartCaptureOnDeviceAsync(LibPcapLiveDevice device, CancellationToken ct)
    {
        var key = device.Name;

        try
        {
            device.Open(DeviceModes.Promiscuous, read_timeout: 1);

            var filter = GenerateFilter();
            if (!string.IsNullOrWhiteSpace(filter))
                device.Filter = filter;

            if (_activeDevices.TryAdd(key, device))
            {
                _logger.LogInformation("Capturing on device {Name} with filter: {Filter}",
                    device.Name, device.Filter);
            }

            device.OnPacketArrival += OnPacketArrival; // Register the OnPacketArrival event handler
            device.StartCapture(); // Start capturing packets

            while (!ct.IsCancellationRequested)
                await Task.Delay(250, ct); // Wait for 250ms before checking for cancellation

            device.StopCapture(); // Stop capturing packets
            device.Close(); // Close the device

            _logger.LogInformation("Stopped capturing packets from device {Name}", device.Name);
        }
        catch (OperationCanceledException) { /* normal on shutdown */ }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error starting capture on device {Name}", device.Name);
        }
        finally
        {
            if (_activeDevices.TryRemove(key, out var dev))
            {
                try { dev.OnPacketArrival -= OnPacketArrival; } catch { /* ignore */ } // Unregister the OnPacketArrival event handler
                try { if (dev.Started) dev.StopCapture(); } catch { /* ignore */ } // Stop capturing packets
                try { dev.Close(); } catch { /* ignore */ } // Close the device
            }
        }
    }

    private void OnPacketArrival(object? sender, PacketCapture e)
    {
        try
        {
            if (sender is not LibPcapLiveDevice) return;

            var raw = e.GetPacket();
            if (raw?.Data is null || raw.Data.Length == 0) return;

            // Zero-copy: wrap raw byte[] as ReadOnlyMemory<byte>
            var payload = new ReadOnlyMemory<byte>(raw.Data);

            var parsed = PacketParser(payload); // Generic parser for the packet
            if (parsed is null) return;

            // Delegate handling (storage / pipeline / realtime) to consumer
            _ = Task.Run(async () =>
            {
                try { await PacketHandler(parsed); } // Delegate handling (storage / pipeline / realtime) to consumer
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Packet handler failed");
                }
            });
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "OnPacketArrival error");
        }
    }

    /// <summary>
    /// Starts packet capture on all devices
    /// </summary>
    public async Task StartCaptureAsync()
    {
        lock (_captureLock)
        {
            if (_isCapturing)
            {
                _logger.LogWarning("Capture is already running");
                return;
            }
            _isCapturing = true;
        }

        try
        {
            _logger.LogInformation("Starting packet capture with filter: {Filter}", GenerateFilter());

            var all = CaptureDeviceList.Instance.OfType<LibPcapLiveDevice>().ToList();
            if (all.Count == 0)
            {
                _logger.LogError("No capture devices found. Install libpcap/Npcap.");
                return;
            }

            var devices = _activeDevices.Values.ToList();
            if (devices.Count == 0)
            {
                _logger.LogWarning("No devices selected.");
                return;
            }

            // Start capture on all selected devices
            var tasks = new List<Task>(devices.Count);
            tasks.AddRange(devices.Select(dev => StartCaptureOnDeviceAsync(dev, CancellationToken.None)));
            
            await Task.WhenAll(tasks);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error starting packet capture");
            lock (_captureLock)
            {
                _isCapturing = false;
            }
        }
    }

    /// <summary>
    /// Stops packet capture on all devices
    /// </summary>
    public async Task StopCaptureAsync()
    {
        lock (_captureLock)
        {
            if (!_isCapturing)
            {
                _logger.LogWarning("Capture is not running");
                return;
            }
            _isCapturing = false;
        }

        try
        {
            _logger.LogInformation("Stopping packet capture");

            foreach (var kv in _activeDevices)
            {
                var dev = kv.Value;
                try
                {
                    try { dev.OnPacketArrival -= OnPacketArrival; } catch { /* ignore */ }
                    try { if (dev.Started) dev.StopCapture(); } catch { /* ignore */ }
                    try { dev.Close(); } catch { /* ignore */ }
                }
                catch { /* best-effort */ }
            }
            _activeDevices.Clear();

            _logger.LogInformation("Packet capture stopped");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error stopping packet capture");
        }
    }

    /// <summary>
    /// Gets the current capture status
    /// </summary>
    public bool IsCapturing => _isCapturing;

    public override void Dispose()
    {
        try
        {
            StopCaptureAsync().Wait();
        }
        catch { /* best-effort */ }

        base.Dispose();
    }
}
