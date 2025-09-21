namespace PacketProcessing.Services.Networking;

using System.Collections.Concurrent;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using SharpPcap;
using SharpPcap.LibPcap;
using System.Threading.Channels;
using Microsoft.Extensions.Configuration;
using PacketProcessing.Entities;
using PacketProcessing.Utils.Observers;
using System.Net;
using System.Net.Sockets;
using PacketDotNet;

public abstract class BaseCaptureService<T> : BackgroundService, IObservable<T> where T : BasePacketEntity
{
    protected ILogger<BaseCaptureService<T>> _logger;  
    internal string _protocol;
    internal int? _port;
    internal IReadOnlyList<string> _ips;
    internal ConcurrentDictionary<string, LibPcapLiveDevice> _activeDevices;

    protected Channel<T> _channel; 
    internal delegate T? PacketParser(ReadOnlySpan<byte> payload);
    internal delegate ValueTask PacketHandler(T packet);
    internal PacketParser? _packetParser;
    internal PacketHandler? _packetHandler;

    internal bool _isCapturing = false;
    internal readonly object _captureLock = new();
    private CancellationTokenSource? _captureCts;

    // Observer pattern implementation
    private readonly List<IObserver<T>> _observers = [];
    private readonly object _observersLock = new();

    // Performance counters for high-throughput monitoring
    private long _packetsProcessed = 0;
    private long _packetsDropped = 0;
    private long _packetsCaptured = 0;
    private DateTime _lastStatsTime = DateTime.UtcNow;
    private readonly object _statsLock = new();

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
        if (string.IsNullOrWhiteSpace(_protocol))
            throw new ArgumentException("Protocol must be provided", nameof(_protocol));

        // Build protocol expression
        string protocolExpr;
        if (_protocol.Equals("http", StringComparison.InvariantCultureIgnoreCase))
        {
            protocolExpr = "tcp port 80";
        }
        else
        {
            protocolExpr = _protocol.ToLowerInvariant();
        }

        // Get IP addresses to filter by
        var ips = _ips?.Where(s => !string.IsNullOrWhiteSpace(s)).ToList() ?? [];
        if (ips.Count == 0) return protocolExpr;

        // Build IP filter clauses
        var hostClauses = new List<string>();
        foreach (var s in ips)
        {
            if (IPAddress.TryParse(s, out var ip))
            {
                if (ip.AddressFamily == AddressFamily.InterNetworkV6)
                {
                    hostClauses.Add($"ip6 host {s}");
                }
                else // IPv4
                {
                    hostClauses.Add($"ip host {s}");
                    // Special case: include IPv6 loopback alongside 127.0.0.1
                    if (s == "127.0.0.1")
                        hostClauses.Add("ip6 host ::1");
                }
            }
            else
            {
                // If a hostname is provided, let libpcap resolve it
                hostClauses.Add($"host {s}");
            }
        }

        // Combine protocol and IP filters
        var hostsExpr = "(" + string.Join(" or ", hostClauses) + ")";
        return $"{protocolExpr} and {hostsExpr}";
    }

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        try
        {
            _logger.LogInformation("Capture service initialized {DataPipeName}. Waiting for start signal...", typeof(T).Name);
            _logger.LogInformation("Service Configuration - Name: {ServiceName}, Entity: {EntityType}, Protocol: {Protocol}, Port: {Port}, IPs: {IPs}", 
                GetType().Name, typeof(T).Name, _protocol, _port?.ToString() ?? "any", string.Join(", ", _ips));

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
            _captureCts = new CancellationTokenSource();
        }

        try
        {
            var filter = GenerateFilter();
            _logger.LogInformation("Starting packet capture with filter: {Filter}", filter);
            _logger.LogDebug("Capture configuration - Protocol: {Protocol}, IPs: {IPs}", _protocol, string.Join(", ", _ips));

            var baseList = CaptureDeviceList.Instance.OfType<LibPcapLiveDevice>().ToList();
            if (baseList.Count == 0)
            {
                _logger.LogError("No capture devices found. Install libpcap/Npcap.");
                return;
            }

            _logger.LogInformation("Found {Count} capture devices: {Devices}", 
                baseList.Count, string.Join(", ", baseList.Select(d => d.Name)));

            // Auto-select devices if none are provided
            if (_activeDevices.IsEmpty)
            {
                _logger.LogDebug("No devices pre-selected, auto-selecting all available devices for capture");
                
                // Add all available devices to capture from
                foreach (var baseDev in baseList)
                {
                    try
                    {
                        var dev = new LibPcapLiveDevice(baseDev.Interface ?? throw new Exception("Interface is null"));
                        if (_activeDevices.TryAdd(baseDev.Name, dev))
                        {
                            _logger.LogDebug("{Name} instanceId={Id}", dev.Name,
                                System.Runtime.CompilerServices.RuntimeHelpers.GetHashCode(dev));                        
                        }
                    }
                    catch (Exception ex)
                    {
                        _logger.LogWarning(ex, "Failed to add device {DeviceName}", baseDev.Name);
                    }
                }
            }

            // If still no devices, try to use the first available device
            if (_activeDevices.IsEmpty && baseList.Count > 0)
            {
                var firstDevice = baseList.First();
                _logger.LogWarning("No devices selected, using first available device: {DeviceName}", firstDevice.Name);
                _activeDevices.TryAdd(firstDevice.Name, firstDevice);
            }

            var devices = _activeDevices.Values.ToList();
            if (devices.Count == 0)
            {
                _logger.LogWarning("No devices selected for capture.");
                return;
            }

            _logger.LogInformation("Starting capture on {DeviceCount} devices", devices.Count);

            // Start capture on all selected devices
            // Fire-and-forget device tasks. Use capture CTS so StopCaptureAsync can cancel.
            foreach (var dev in devices)
            {
                _logger.LogInformation("Starting capture task for device {Name}", dev.Name);
                _ = Task.Run(async () => await StartCaptureOnDeviceAsync(dev, _captureCts!.Token));
            }
            
            // Yield once to let device tasks spin up
            await Task.Yield();
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

            try { _captureCts?.Cancel(); } catch { }

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

    /// <summary>
    /// Gets current performance statistics (non-resetting)
    /// </summary>
    public (long Processed, long Dropped, double Pps) GetPerformanceStats()
    {
        var now = DateTime.UtcNow;
        var timeDiff = (now - _lastStatsTime).TotalSeconds;
        
        var processed = Interlocked.Read(ref _packetsProcessed);
        var dropped = Interlocked.Read(ref _packetsDropped);
        var pps = timeDiff > 0 ? processed / timeDiff : 0;
        
        return (processed, dropped, pps);
    }

    /// <summary>
    /// Gets current packet statistics (captured, processed, dropped)
    /// </summary>
    public (long Captured, long Processed, long Dropped) GetPacketStats()
    {
        return (Interlocked.Read(ref _packetsCaptured), 
                Interlocked.Read(ref _packetsProcessed), 
                Interlocked.Read(ref _packetsDropped));
    }

    private async Task StartCaptureOnDeviceAsync(LibPcapLiveDevice device, CancellationToken ct)
    {
        var key = device.Name;

        try
        {
            _logger.LogInformation("Opening device {Name} for capture", device.Name);
            device.Open(DeviceModes.None, read_timeout: 10);
            _logger.LogInformation("Device {Name} opened successfully", device.Name);

            var filter = GenerateFilter();
            if (!string.IsNullOrWhiteSpace(filter))
            {
                device.Filter = filter;
                _logger.LogInformation("Applied filter '{Filter}' to device {Name}", filter, device.Name);
            }

            // Make sure the device is added to the active devices
            _activeDevices.TryAdd(key, device);
            
            _logger.LogInformation("Capturing on device {Name} with filter: {Filter}",
                device.Name, device.Filter);

            device.OnPacketArrival += OnPacketArrival; // Register the OnPacketArrival event handler
            device.StartCapture(); // Start capturing packets

            // Wait for cancellation - no need for polling loop since packet capture is event-driven
            await Task.Delay(Timeout.Infinite, ct);

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
        // Increment captured counter for every packet that arrives
        var captured = Interlocked.Increment(ref _packetsCaptured);

        // Ultra-fast path - single null check, no try-catch
        if (_packetParser is null || _packetHandler is null) 
        {
            Interlocked.Increment(ref _packetsDropped);
            _logger.LogWarning("Packet dropped: Parser or handler not initialized for {ServiceType}", typeof(T).Name);
            LogPacketStatsIfNeeded(captured);
            return;
        }

        try
        {
            // Use the same approach as the working POC - get RawCapture first
            var rawPacket = e.GetPacket();
            if (rawPacket == null)
            {
                Interlocked.Increment(ref _packetsDropped);
                _logger.LogWarning("Packet dropped: No raw packet data from {Device}", e.Device?.Name ?? "unknown");
                LogPacketStatsIfNeeded(captured);
                return;
            }

            var packetData = rawPacket.Data;
            if (packetData == null || packetData.Length == 0)
            {
                Interlocked.Increment(ref _packetsDropped);
                _logger.LogWarning("Packet dropped: Empty packet data from {Device}", e.Device?.Name ?? "unknown");
                LogPacketStatsIfNeeded(captured);
                return;
            }

            _logger.LogDebug("Raw packet received: {Length} bytes from {Device}", packetData.Length, e.Device?.Name ?? "unknown");

            // Parse the packet using the extracted payload
            var parsed = _packetParser.Invoke(packetData);
            if (parsed is null) 
            {
                Interlocked.Increment(ref _packetsDropped);
                _logger.LogWarning("Packet parsing failed: Unable to parse packet of {Length} bytes. Raw data: {HexData}", 
                    packetData.Length, 
                    packetData.Length > 32 ? Convert.ToHexString(packetData[..32]) + "..." : Convert.ToHexString(packetData));
                LogPacketStatsIfNeeded(captured);
                return;
            }

            _logger.LogDebug("Packet parsed successfully: {Type} - {Details}", 
                typeof(T).Name, 
                parsed.ToString() ?? "No details available");

            // Delegate handling (storage / pipeline / realtime) to consumer
            var vt = _packetHandler.Invoke(parsed);
            if (!vt.IsCompletedSuccessfully)
            {
                _ = vt.AsTask(); // schedule continuation; no blocking, no extra Task when already completed
                Interlocked.Increment(ref _packetsProcessed);
                _logger.LogDebug("Packet processed successfully: {Type}", typeof(T).Name);
            }

            // Increment processed counter
            LogPacketStatsIfNeeded(captured);
        }
        catch (Exception ex)
        {
            Interlocked.Increment(ref _packetsDropped);
            _logger.LogDebug(ex, "Packet dropped: Exception during processing");
            LogPacketStatsIfNeeded(captured);
        }
    }

    private void LogPacketStatsIfNeeded(long captured)
    {
        var processed = Interlocked.Read(ref _packetsProcessed);
        
        // Log statistics every 100 processed packets (like POC), or every 1000 captured packets if no processing
        if ((processed > 0 && processed % 100 == 0) || (processed == 0 && captured > 0 && captured % 1000 == 0))
        {
            var dropped = Interlocked.Read(ref _packetsDropped);
            var successRate = captured > 0 ? (double)processed / captured : 0.0;
            
            _logger.LogInformation("Capture Statistics: Captured {TotalCaptured}, Processed {TotalProcessed}, Dropped: {TotalDropped}, Success Rate: {SuccessRate:P1}", 
                captured, processed, dropped, successRate);
        }
    }

    #region IObservable<T> Implementation

    /// <summary>
    /// Subscribes an observer to receive packet updates
    /// </summary>
    /// <param name="observer">The observer to subscribe</param>
    public void Subscribe(IObserver<T> observer)
    {
        if (observer == null) return;
        
        lock (_observersLock)
        {
            if (!_observers.Contains(observer))
            {
                _observers.Add(observer);
                _logger.LogDebug("Observer {ObserverType} subscribed to {ServiceType}", 
                    observer.GetType().Name, typeof(T).Name);
            }
        }
    }

    /// <summary>
    /// Unsubscribes an observer from receiving packet updates
    /// </summary>
    /// <param name="observer">The observer to unsubscribe</param>
    public void Unsubscribe(IObserver<T> observer)
    {
        if (observer == null) return;
        
        lock (_observersLock)
        {
            if (_observers.Remove(observer))
            {
                _logger.LogDebug("Observer {ObserverType} unsubscribed from {ServiceType}", 
                    observer.GetType().Name, typeof(T).Name);
            }
        }
    }

    /// <summary>
    /// Notifies all subscribed observers with a captured packet
    /// </summary>
    /// <param name="packet">The packet to notify observers about</param>
    public void NotifyObservers(T packet)
    {
        if (packet == null) return;

        lock (_observersLock)
        {
            foreach (var observer in _observers)
            {
                try
                {
                    observer.Update(packet);
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Error notifying observer {ObserverType}", observer.GetType().Name);
                }
            }
        }
    }

    #endregion

    /// <summary>
    /// Disposes the capture service
    /// </summary>
    public override void Dispose()
    {
        try
        {
            StopCaptureAsync().Wait();
            GC.SuppressFinalize(this);
        }
        catch { /* best-effort */ }

        base.Dispose();
    }
}
