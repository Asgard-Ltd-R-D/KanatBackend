using System.Threading.Channels;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using PacketProcessing.Entities;
using PacketProcessing.Utils.Parsers;
using PacketProcessing.Utils.Filters;
using System.Runtime.InteropServices;
using System.Buffers;
using PacketProcessing.Utils.Observers;
using PacketProcessing.Services.Transmission;
using PacketProcessing.Entities.Packet;
using PacketProcessing.DTOs.Range;
using PacketProcessing.DTOs.Conf;
namespace PacketProcessing.Services.Realtime.Networking;

public class HandlerService<T> : BackgroundService, IHandlerService<T>, IObserver<RawPacketEvent>, IObservable<BasePacketEntity>
    where T : BasePacketEntity
{
    private readonly ILogger<HandlerService<T>> _logger;
    private readonly StatsObserver _statsObserver;

    // Device filters
    private readonly string _protocol;
    private readonly IEnumerable<string> _ips;

    private readonly ITransmissionService? _transmissionService;

    // Channels
    private readonly Channel<RawPacketEvent> _rawChannel; // device -> handler
    private readonly Channel<T> _parsedChannel;           // handler -> DbWriter
    private readonly int _rawCapacity;

    private readonly int _workerCount;
    
    // Hub transmission
    private readonly TimeSpan _transmissionInterval;

    // Channel counts (manual tracking since bounded channels don't support Reader.Count)
    private long _rawChannelCount;

    private const int RAW_READ_BURST = 64; // Smaller burst for lower latency

    private IDisposable? _subscription;

    private readonly ParseMapper _parseMapper;
    private readonly string _entityName;

    public HandlerService(
        string dataPipeName,
        ITransmissionService transmissionService,
        ILogger<HandlerService<T>> logger,
        Channel<RawPacketEvent> rawChannel,
        int rawCapacity,
        Channel<T> parsedChannel,
        IConfiguration configuration,
        ParseMapper parseMapper,
        StatsObserver statsObserver)
    {
        _logger = logger;
        _rawChannel = rawChannel;
        _rawCapacity = rawCapacity;
        _parsedChannel = parsedChannel;
        _transmissionService = transmissionService;
        _parseMapper = parseMapper;
        _statsObserver = statsObserver;

        _protocol = configuration.GetValue<string>($"{dataPipeName}:Network:Protocol") ?? "";
        _ips = configuration.GetSection($"{dataPipeName}:Network:IPs").Get<IEnumerable<string>>() ?? [];

        _entityName = typeof(T) == typeof(MotionPacketEntity) ? "Motion" :
                      typeof(T) == typeof(SafetyPacketEntity) ? "Safety" :
                      typeof(T) == typeof(OnVIFPacketEntity) ? "OnVIF" : "Unknown";

        var concurrency = configuration.GetSection("Concurrency");
        var min = concurrency.GetValue<int>("MinWorkers", 2);
        var max = concurrency.GetValue<int>("MaxWorkers", 8);
        _workerCount = Math.Clamp(Environment.ProcessorCount, min, max);
        
        // Hub transmission configuration
        _transmissionInterval = TimeSpan.FromMilliseconds(
            configuration.GetValue<int>("HubTransmission:IntervalMs", 30));

        _logger.LogInformation(
            "[HANDLER-SERVICE] {Handler} initialized with {Workers} workers (RawChannelCapacity:{RawCap}, Timeout:{IntervalMs}ms)",
            typeof(T).Name, _workerCount, _rawCapacity, _transmissionInterval.TotalMilliseconds);
    }

    #region IHandlerService

    public async Task SubscribeToDeviceAsync(IDeviceService deviceService, RangeDto.RangeConfig config)
    {
        ArgumentNullException.ThrowIfNull(config);
        ArgumentNullException.ThrowIfNull(config.BpfConfig);

        // Determine endpoint overrides based on handler entity type
        EndpointSpecification[] endpoints = [];
        if (typeof(T) == typeof(MotionPacketEntity))
            endpoints = config.BpfConfig.Motion ?? [];
        else if (typeof(T) == typeof(SafetyPacketEntity))
            endpoints = ToSafetyArray(config.BpfConfig.Safety);
        else if (typeof(T) == typeof(OnVIFPacketEntity))
            endpoints = config.BpfConfig.OnVIF  ?? [];

        if (string.IsNullOrWhiteSpace(config.BpfConfig.Device))
        {
            _logger.LogError("[{Entity}] Missing device in RangeConfig.BpfConfig", typeof(T).Name);
            throw new ArgumentException("Device must be provided in RangeConfig.BpfConfig.Device");
        }

        if (endpoints.Length == 0)
        {
            _logger.LogWarning("[{Entity}] No endpoints provided. Falling back to appsettings IPs.", typeof(T).Name);
        }

        var filter = BpfFilterBuilder.Build(_protocol, endpoints);

        var deviceName = config.BpfConfig.Device;
        try
        {
            _logger.LogInformation("[HANDLER-SERVICE] [{Entity}] Subscribing device {Device} with filter: {Filter}", typeof(T).Name, deviceName, filter);
            await deviceService.SubscribeWithFilterAsync(this, deviceName, filter);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[HANDLER-SERVICE] [{Entity}] Subscribe failed for device {Device}", typeof(T).Name, deviceName);
            throw;
        }
    }

    public async Task SubscribeToDeviceAsync(IDeviceService deviceService, BPFConfDto bpfConfig)
    {
        ArgumentNullException.ThrowIfNull(bpfConfig);

        EndpointSpecification[] endpoints = [];
        if (typeof(T) == typeof(MotionPacketEntity))
            endpoints = bpfConfig.Motion ?? [];
        else if (typeof(T) == typeof(SafetyPacketEntity))
            endpoints = ToSafetyArray(bpfConfig.Safety);
        else if (typeof(T) == typeof(OnVIFPacketEntity))
            endpoints = bpfConfig.OnVIF  ?? [];

        if (string.IsNullOrWhiteSpace(bpfConfig.Device))
        {
            _logger.LogError("[{Entity}] Missing device in BpfConfig", typeof(T).Name);
            throw new ArgumentException("Device must be provided in BpfConfig.Device");
        }

        if (endpoints.Length == 0)
        {
            _logger.LogWarning("[{Entity}] No endpoints provided. Falling back to appsettings IPs.", typeof(T).Name);
        }

        var filter = BpfFilterBuilder.Build(_protocol, endpoints);
        var deviceName = bpfConfig.Device;
        try
        {
            _logger.LogInformation("[HANDLER-SERVICE] [{Entity}] Subscribing device {Device} with filter: {Filter}", typeof(T).Name, deviceName, filter);
            await deviceService.SubscribeWithFilterAsync(this, deviceName, filter);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[HANDLER-SERVICE] [{Entity}] Subscribe failed for device {Device}", typeof(T).Name, deviceName);
            throw;
        }
    }

    [Obsolete("Development only - use SubscribeToDeviceAsync(DeviceService, RangeDto.RangeConfig) instead")]
    public async Task SubscribeToDeviceAsync(IDeviceService deviceService, string deviceName)
    {
        var filter = BpfFilterBuilder.Build(_protocol, _ips);
        await deviceService.SubscribeWithFilterAsync(this, deviceName, filter);
        _logger.LogInformation("[HANDLER-SERVICE] {Handler} subscribed to {Device} with filter {Filter}",
            typeof(T).Name, deviceName, filter);
    }


    public async Task UnsubscribeAsync(IDeviceService deviceService)
    {
        _subscription?.Dispose();
        _subscription = null;
        await deviceService.UnsubscribeAsync(this);

        _statsObserver.Handler.Reset();
        Interlocked.Exchange(ref _rawChannelCount, 0);

        _logger.LogInformation("[HANDLER-SERVICE] {Handler} unsubscribed", typeof(T).Name);
    }

    public (long Captured, long Parsed, long Dropped, double AvgLatencyMs) GetStats()
    {
        return (_statsObserver.Handler.GetCaptured(), 
                _statsObserver.Handler.GetParsed(), 
                _statsObserver.Handler.GetDropped(), 
                _statsObserver.Handler.GetAverageLatency());
    }
    
    public long GetBackpressureEvents() => _statsObserver.Handler.GetBackpressure();
    
    public int GetRawChannelCount()
    {
        var count = Interlocked.Read(ref _rawChannelCount);
        return count >= 0 ? (int)count : 0;
    }
    
    public void ResetStats()
    {
        _statsObserver.Handler.Reset();
        // Note: rawChannelCount is not reset as it represents actual queue state
        
        _logger.LogInformation("[HANDLER-SERVICE] {Handler} statistics reset", typeof(T).Name);
    }

    #endregion

    #region IObserver<RawPacketEvent>

    public void OnNext(RawPacketEvent evt)
    {
        _statsObserver.Handler.IncrementCaptured();
        
        // Try fast path first
        if (_rawChannel.Writer.TryWrite(evt))
        {
            Interlocked.Increment(ref _rawChannelCount);
            // Per-entity capture success
            _statsObserver.IncrementCaptureFor(_entityName, success: true);
            
            // Update channel stats after incrementing
            var currentCount = Interlocked.Read(ref _rawChannelCount);
            var utilization = (double)currentCount / _rawCapacity * 100;
            
            var avgLatency = _statsObserver.Handler.GetAverageLatency();
            if (typeof(T) == typeof(PacketProcessing.Entities.Packet.MotionPacketEntity))
                _statsObserver.UpdateChannelStats("MotionRaw", _rawCapacity, (int)currentCount, utilization, _workerCount, avgLatency);
            else if (typeof(T) == typeof(PacketProcessing.Entities.Packet.SafetyPacketEntity))
                _statsObserver.UpdateChannelStats("SafetyRaw", _rawCapacity, (int)currentCount, utilization, _workerCount, avgLatency);
            else if (typeof(T) == typeof(PacketProcessing.Entities.Packet.OnVIFPacketEntity))
                _statsObserver.UpdateChannelStats("OnvifRaw", _rawCapacity, (int)currentCount, utilization, _workerCount, avgLatency);
            
            return;
        }

        // Channel full - Wait mode will block to guarantee delivery
        _statsObserver.Handler.IncrementBackpressure();
        
        // This blocks until space available (guarantees packet is written)
        _rawChannel.Writer
            .WriteAsync(evt, CancellationToken.None)
            .AsTask()
            .GetAwaiter()
            .GetResult();
        
        Interlocked.Increment(ref _rawChannelCount);
        _statsObserver.IncrementCaptureFor(_entityName, success: true);
        
        // Update channel stats after incrementing
        var finalCount = Interlocked.Read(ref _rawChannelCount);
        var finalUtilization = (double)finalCount / _rawCapacity * 100;
        
        var avgLatency2 = _statsObserver.Handler.GetAverageLatency();
        if (typeof(T) == typeof(PacketProcessing.Entities.Packet.MotionPacketEntity))
            _statsObserver.UpdateChannelStats("MotionRaw", _rawCapacity, (int)finalCount, finalUtilization, _workerCount, avgLatency2);
        else if (typeof(T) == typeof(PacketProcessing.Entities.Packet.SafetyPacketEntity))
            _statsObserver.UpdateChannelStats("SafetyRaw", _rawCapacity, (int)finalCount, finalUtilization, _workerCount, avgLatency2);
        else if (typeof(T) == typeof(PacketProcessing.Entities.Packet.OnVIFPacketEntity))
            _statsObserver.UpdateChannelStats("OnvifRaw", _rawCapacity, (int)finalCount, finalUtilization, _workerCount, avgLatency2);
    }

    public void OnError(Exception error) =>
        _logger.LogError(error, "Device service signaled error");

    public void OnCompleted()
    {
        _logger.LogInformation("Device service completed");
        _rawChannel.Writer.Complete();
    }

    #endregion

    #region BackgroundService

    protected override Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var workers = Enumerable.Range(0, _workerCount)
            .Select(i => Task.Factory.StartNew(
                () => WorkerLoopAsync(i, stoppingToken),
                stoppingToken,
                TaskCreationOptions.LongRunning,
                TaskScheduler.Default).Unwrap())
            .ToArray();

        return Task.WhenAll(workers);
    }

    private async Task WorkerLoopAsync(int workerId, CancellationToken token)
    {
        // Reuse buffers to avoid per-iteration allocs
        var rawBatch = new List<RawPacketEvent>(RAW_READ_BURST);
        
        try
        {
            while (!token.IsCancellationRequested)
            {
                rawBatch.Clear();
                int batchParsed = 0;
                int batchDropped = 0;
                int batchBackpressure = 0;

                // ---- 1) Block for first item (start a mini-batch) ----
                RawPacketEvent first;
                try
                {
                    first = await _rawChannel.Reader.ReadAsync(token);
                }
                catch (ChannelClosedException)
                {
                    break; // upstream completed
                }
                rawBatch.Add(first);

                // ---- 2) Aggressively drain what's immediately available ----
                Interlocked.Decrement(ref _rawChannelCount);
                
                while (rawBatch.Count < RAW_READ_BURST && _rawChannel.Reader.TryRead(out var more))
                {
                    rawBatch.Add(more);
                    Interlocked.Decrement(ref _rawChannelCount);
                }
                
                // Do not update raw channel stats here to avoid overwriting enqueue-based telemetry with near-zero after drains

                // ---- 3) Parse and forward ----
                DateTime? firstParsedTimestamp = null;
                DateTime? lastParsedTimestamp = null;
                
                for (int i = 0; i < rawBatch.Count; i++)
                {
                    var raw = rawBatch[i];
                    ArraySegment<byte> segment = default;
                    try
                    {
                        var parsed = Parse(raw.Data.Span);

                        if (parsed is null)
                        {
                            _statsObserver.Handler.IncrementDropped();
                            batchDropped++;
                            _statsObserver.IncrementParseFor(_entityName, success: false);
                            continue;
                        }

                        parsed.Timestamp = raw.Timestamp; // Override the timestamp to the actual timestamp of the packet

                        _transmissionService?.OnNext(parsed);
    
                        // Track timestamps for latency measurement
                        if (firstParsedTimestamp == null)
                            firstParsedTimestamp = parsed.Timestamp;
                        lastParsedTimestamp = parsed.Timestamp;
                        
                        // Try fast path to parsed channel; otherwise await (true backpressure)
                        if (!_parsedChannel.Writer.TryWrite(parsed))
                        {
                            _statsObserver.Handler.IncrementBackpressure();
                            batchBackpressure++;
                            await _parsedChannel.Writer.WriteAsync(parsed, token);
                            // Parsed item enqueued to parsed channel -> increment parsed channel count
                            _statsObserver.DbWriter.IncrementChannelCount();
                        }
                        else
                        {
                            // Parsed item enqueued to parsed channel -> increment parsed channel count
                            _statsObserver.DbWriter.IncrementChannelCount();
                        }

                        _statsObserver.Handler.IncrementParsed();
                        _statsObserver.IncrementParseFor(_entityName, success: true);
                        batchParsed++;
                    }
                    catch
                    {
                        _statsObserver.Handler.IncrementDropped();
                        batchDropped++;
                    }
                    finally
                    {
                        // Return pooled memory *after* processing is done
                        if (MemoryMarshal.TryGetArray(raw.Data, out segment) && segment.Array is not null)
                            ArrayPool<byte>.Shared.Return(segment.Array);
                    }
                }

                // ---- 4) Log every parsing batch with stats ----
                var totalCaptured = _statsObserver.Handler.GetCaptured();
                var totalParsed = _statsObserver.Handler.GetParsed();
                var totalDropped = _statsObserver.Handler.GetDropped();
                var totalBackpressure = _statsObserver.Handler.GetBackpressure();
                
                // Calculate parsing latency from this batch
                var parsingLatencyMs = 0.0;
                if (batchParsed > 0 && lastParsedTimestamp.HasValue)
                {
                    // Measure actual time from packet creation to being sent to DB writer
                    parsingLatencyMs = (DateTime.UtcNow - lastParsedTimestamp.Value).TotalMilliseconds;
                }
                
                _statsObserver.Handler.AddLatency((long)parsingLatencyMs);
                _logger.LogInformation(
                    "[HANDLER-SERVICE] [PARSER] {Entity} Worker {Worker}: Batch=(Parsed:{BatchParsed} Dropped:{BatchDropped} BP:{BatchBP} Latency:{Latency:F1}ms) Total=(Captured:{TotalCaptured} Parsed:{TotalParsed} Dropped:{TotalDropped} BP:{TotalBP})",
                    typeof(T).Name, workerId, batchParsed, batchDropped, batchBackpressure, parsingLatencyMs, totalCaptured, totalParsed, totalDropped, totalBackpressure);
            }
        }

        catch (OperationCanceledException) { }
    }

    #endregion

    private T? Parse(ReadOnlySpan<byte> raw)
    {
        if (raw.IsEmpty) return null;
        try { return _parseMapper.Map<T>(raw); }
        catch { return null; }
    }

    private static EndpointSpecification[] ToSafetyArray(BPFConfDto.SafetyConf? safety)
    {
        if (safety is null) return [];
        var list = new List<EndpointSpecification>(2);
        if (safety.Sbe is EndpointSpecification sbe)
        {
            list.Add(new EndpointSpecification(sbe.IP, sbe.Port));
        }
        if (safety.Pbe is EndpointSpecification pbe)
        {
            list.Add(new EndpointSpecification(pbe.IP, pbe.Port));
        }
        return [.. list];
    }

    public IDisposable Subscribe(IObserver<BasePacketEntity> observer)
    {
        ArgumentNullException.ThrowIfNull(observer);
        return new Unsubscriber<BasePacketEntity>([observer], observer);
    }
    
    private void UpdateRawChannelStats()
    {
        var rawChannelCount = Interlocked.Read(ref _rawChannelCount);
        var rawCapacity = _rawCapacity;
        var rawUtilization = rawCapacity > 0 ? (double)rawChannelCount / rawCapacity * 100 : 0;
        
        // Determine channel name based on packet type
        var channelName = typeof(T).Name switch
        {
            nameof(MotionPacketEntity) => "MotionRaw",
            nameof(SafetyPacketEntity) => "SafetyRaw", 
            nameof(OnVIFPacketEntity) => "OnvifRaw",
            _ => "UnknownRaw"
        };
        
        _statsObserver.UpdateChannelStats(channelName, rawCapacity, (int)rawChannelCount, rawUtilization);
    }
}
