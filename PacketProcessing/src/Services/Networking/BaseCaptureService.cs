namespace PacketProcessing.Services.Networking;

using System.Collections.Concurrent;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using SharpPcap;
using SharpPcap.LibPcap;
using System.Threading.Channels;
using Microsoft.Extensions.Configuration;
using PacketProcessing.Entities;
using PacketProcessing.Utils;

public abstract class BaseCaptureService<T> : BackgroundService where T : BasePacketEntity
{
    protected ILogger<BaseCaptureService<T>> _logger;  
    internal string _protocol;
    internal IReadOnlyList<string> _ips;
    internal ConcurrentDictionary<string, LibPcapLiveDevice> _activeDevices;

    protected Channel<T> _channel; 
    internal delegate T? PacketParser(ReadOnlySpan<byte> payload);
    internal delegate ValueTask PacketHandler(T packet);
    internal PacketParser? _packetParser;
    internal PacketHandler? _packetHandler;

    internal bool _isCapturing = false;
    internal readonly object _captureLock = new();

    public BaseCaptureService(
        ILogger<BaseCaptureService<T>> logger,
        IConfiguration configurationManager,
        Channel<T> channel,
        string dataPipeName)
    {
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _channel = channel ?? throw new ArgumentNullException(nameof(channel));
        _activeDevices = new ConcurrentDictionary<string, LibPcapLiveDevice>();

        // Get configuration for this specific DataPipe
        var dataPipeSection = configurationManager.GetSection("DataPipes").GetSection(dataPipeName);
        var networkSection = dataPipeSection.GetSection("Network");
        
        // Get network configuration
        _protocol = networkSection.GetValue<string>("Protocol") ?? "tcp";
        _ips = networkSection.GetSection("IPs").Get<string[]>() ?? [];
    }
    
    internal virtual string GenerateFilter()
    {
        var ipExpr = string.Join(" or ", _ips.Select(ip => $"host {ip}")); // Generate a filter for the given IPs as "192.168.1.1 or 192.168.1.2"

        return $"{_protocol} and ({ipExpr})";// Final output is "tcp and (host 192.168.1.1 or host 192.168.1.2)"
    }

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        try
        {
            _logger.LogInformation("Capture service initialized {DataPipeName}. Waiting for start signal...", typeof(T).Name);

            // Wait for cancellation (application shutdown) without starting capture
            while (!ct.IsCancellationRequested)
            {
                await Task.Delay(1000, ct);

                if (_packetParser is null || _packetHandler is null)
                {
                    await StopCaptureAsync();
                    throw new Exception("Packet parser and handler are not set");                
                }
            }
        }
        catch (OperationCanceledException) { /* normal on shutdown */ }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error in packet capture service");
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

            // Auto-select devices if none are provided
            if (_activeDevices.IsEmpty)
            {
                _logger.LogInformation("No devices pre-selected, auto-selecting all available devices for capture");
                
                // Add all available devices to capture from
                foreach (var device in all)
                {
                    try
                    {
                        if (_activeDevices.TryAdd(device.Name, device))
                        {
                            _logger.LogInformation("Auto-selected device: {DeviceName}", device.Name);
                        }
                    }
                    catch (Exception ex)
                    {
                        _logger.LogWarning(ex, "Failed to add device {DeviceName}", device.Name);
                    }
                }
            }

            var devices = _activeDevices.Values.ToList();
            if (devices.Count == 0)
            {
                _logger.LogWarning("No devices selected for capture.");
                return;
            }

            _logger.LogInformation("Starting capture on {DeviceCount} devices", devices.Count);

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
    public Task StopCaptureAsync()
    {
        lock (_captureLock)
        {
            if (!_isCapturing)
            {
                _logger.LogWarning("Capture is not running");
                return Task.CompletedTask;
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

        return Task.CompletedTask;
    }

    /// <summary>
    /// Gets the current capture status
    /// </summary>
    public bool IsCapturing => _isCapturing;

    /// <summary>
    /// Gets the current channel
    /// </summary>  
    public Channel<T> GetChannel => _channel;

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
                _logger.LogDebug("Capturing on device {Name} with filter: {Filter}",
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

    internal void OnPacketArrival(object? sender, PacketCapture e)
    {
        try
        {
            if (sender is not LibPcapLiveDevice) return;
            if (_packetParser is null || _packetHandler is null) return;

            // Get the raw packet data and check if it is empty
            ReadOnlySpan<byte> span = e.Data;
            if (span.IsEmpty) return;

            _logger.LogDebug("Packet arrived: {Length} bytes", span.Length);

            // Parse the packet using the extracted payload
            var parsed = _packetParser.Invoke(span);
            if (parsed is null)
            {
                _logger.LogDebug("Packet parsing failed");
                return;
            }

            _logger.LogDebug("Packet parsed successfully: {Type}", parsed.GetType().Name);

            // Delegate handling (storage / pipeline / realtime) to consumer
            var vt = _packetHandler.Invoke(parsed);
            if (!vt.IsCompletedSuccessfully)
            {
                _ = vt.AsTask(); // schedule continuation; no blocking, no extra Task when already completed
            }

            _logger.LogDebug("Packet handled successfully");
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "OnPacketArrival error");
        }
    }

    /// <summary>
    /// Disposes the capture service
    /// </summary>
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
