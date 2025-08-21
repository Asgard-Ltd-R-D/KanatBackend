namespace PacketProcessing.Capture;
using System.Collections.Concurrent;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using SharpPcap;
using SharpPcap.LibPcap;
using System.Threading.Channels;
using Microsoft.Extensions.Configuration;

public abstract class BaseCaptureService<T> : BackgroundService where T : class
{
    protected ILogger<BaseCaptureService<T>> _logger;  
    protected string _protocol;
    protected IReadOnlyList<string> _ips;
    protected ConcurrentDictionary<string, LibPcapLiveDevice> _activeDevices;
    protected Channel<T> _channel; 
    protected abstract Func<ReadOnlyMemory<byte>, T> PacketParser { get; set; }
    protected abstract Func<T, Task> PacketHandler { get; set; }

    private int _maxChannelCapacity;
    private int _maxWorkers;
    private int _minWorkers;
    private int _currentQueueSize;
    private int _currentNumWorkers;

    public BaseCaptureService(string protocol,
    IReadOnlyList<string> ips,
    ConcurrentDictionary<string,
    LibPcapLiveDevice> activeDevices,
    ILogger<BaseCaptureService<T>> logger,
    IConfiguration configurationManager,
    string dataPipeName)
    {
        _protocol = protocol;
        _ips = ips;
        _activeDevices = activeDevices;
        _logger = logger;
        
        // Get configuration for this specific DataPipe
        var dataPipeConfig = configurationManager.GetSection("DataPipes").GetSection(dataPipeName).GetSection("Channel").GetSection("Members").Get<int>();
        var concurrencyConfig = configurationManager.GetSection("Concurrency").GetSection("MaxWorkers").Get<int>();
        var minWorkers = configurationManager.GetSection("Concurrency").GetSection("MinWorkers").Get<int>();
        
        // Use configuration values instead of hardcoded ones
        _maxChannelCapacity = dataPipeConfig;
        _maxWorkers = concurrencyConfig;
        _minWorkers = minWorkers;
        
        _channel = Channel.CreateUnbounded<T>(new UnboundedChannelOptions {
            SingleWriter = false,
            SingleReader = true,
        });

        _maxChannelCapacity = concurrencyConfig;
        _maxWorkers = concurrencyConfig;
        _minWorkers = minWorkers;
        _currentNumWorkers = minWorkers;

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
            _logger.LogInformation("Starting sniffer with filter: {Filter}", GenerateFilter());

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
            tasks.AddRange(devices.Select(dev => StartCaptureOnDeviceAsync(dev, ct)));
            
            await Task.WhenAll(tasks);
        }
        catch (OperationCanceledException) { /* normal on shutdown */ }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error in packet capture worker");
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

    public override void Dispose()
    {
        foreach (var kv in _activeDevices)
        {
            var dev = kv.Value;
            try
            {
                try { dev.OnPacketArrival -= OnPacketArrival; } catch { /* ignore */ } // Unregister the OnPacketArrival event handler
                try { if (dev.Started) dev.StopCapture(); } catch { /* ignore */ } // Stop capturing packets
                try { dev.Close(); } catch { /* ignore */ } // Close the device
            }
            catch { /* best-effort */ }
        }
        _activeDevices.Clear();

        base.Dispose();
    }
}
