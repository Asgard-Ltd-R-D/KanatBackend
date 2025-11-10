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
using PacketProcessing.Utils.Constants;
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

        _entityName = GetEntityName();

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

        var endpoints = GetEndpointsFromRangeConfig(config.BpfConfig);
        var filter = BpfFilterBuilder.Build(_protocol, endpoints);
        var deviceName = config.BpfConfig.Device;

        if (string.IsNullOrWhiteSpace(deviceName))
        {
            _logger.LogError("[{Entity}] Missing device in RangeConfig.BpfConfig", typeof(T).Name);
            throw new ArgumentException("Device must be provided in RangeConfig.BpfConfig.Device");
        }

        if (endpoints.Length == 0)
        {
            _logger.LogWarning("[{Entity}] No endpoints provided. Falling back to appsettings IPs.", typeof(T).Name);
        }

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

        var endpoints = GetEndpointsFromBpfConfig(bpfConfig);
        var filter = BpfFilterBuilder.Build(_protocol, endpoints);
        var deviceName = bpfConfig.Device;

        if (string.IsNullOrWhiteSpace(deviceName))
        {
            _logger.LogError("[{Entity}] Missing device in BpfConfig", typeof(T).Name);
            throw new ArgumentException("Device must be provided in BpfConfig.Device");
        }

        if (endpoints.Length == 0)
        {
            _logger.LogWarning("[{Entity}] No endpoints provided. Falling back to appsettings IPs.", typeof(T).Name);
        }

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
            UpdateRawChannelStats();
            return;
        }

        // Channel full - Wait mode will block to guarantee delivery
        _statsObserver.Handler.IncrementBackpressure();
        _rawChannel.Writer
            .WriteAsync(evt, CancellationToken.None)
            .AsTask()
            .GetAwaiter()
            .GetResult();
        
        Interlocked.Increment(ref _rawChannelCount);
        _statsObserver.IncrementCaptureFor(_entityName, success: true);
        UpdateRawChannelStats();
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

                // Read batch from channel
                if (!await ReadBatchFromChannelAsync(rawBatch, token))
                    break;
                
                // Process batch: parse and forward
                var batchResult = await ProcessBatchAsync(rawBatch, token);

                // Log batch statistics
                LogBatchStats(workerId, batchResult);
            }
        }
        catch (OperationCanceledException) { }
    }

    private async Task<bool> ReadBatchFromChannelAsync(List<RawPacketEvent> batch, CancellationToken token)
    {
        // Block for first item
        RawPacketEvent first;
        try
        {
            first = await _rawChannel.Reader.ReadAsync(token);
        }
        catch (ChannelClosedException)
        {
            return false; // upstream completed
        }
        
        batch.Add(first);
        Interlocked.Decrement(ref _rawChannelCount);
        
        // Aggressively drain what's immediately available
        while (batch.Count < RAW_READ_BURST && _rawChannel.Reader.TryRead(out var more))
        {
            batch.Add(more);
            Interlocked.Decrement(ref _rawChannelCount);
        }
        
        return true;
    }

    private async Task<BatchProcessResult> ProcessBatchAsync(List<RawPacketEvent> batch, CancellationToken token)
    {
        int parsed = 0;
        int dropped = 0;
        int backpressure = 0;
        DateTime? lastParsedTimestamp = null;

        foreach (var raw in batch)
        {
            ArraySegment<byte> segment = default;
            try
            {
                var parsedEntity = Parse(raw.Data.Span);
                if (parsedEntity is null)
                {
                    RecordParseFailure();
                    dropped++;
                    continue;
                }

                parsedEntity.Timestamp = raw.Timestamp;
                _transmissionService?.OnNext(parsedEntity);
                
                if (lastParsedTimestamp == null || parsedEntity.Timestamp > lastParsedTimestamp.Value)
                    lastParsedTimestamp = parsedEntity.Timestamp;
                
                // Forward to parsed channel
                if (await ForwardToParsedChannelAsync(parsedEntity, token))
                    backpressure++;

                RecordParseSuccess();
                parsed++;
            }
            catch
            {
                RecordParseFailure();
                dropped++;
            }
            finally
            {
                // Return pooled memory after processing
                if (MemoryMarshal.TryGetArray(raw.Data, out segment) && segment.Array is not null)
                    ArrayPool<byte>.Shared.Return(segment.Array);
            }
        }

        // Calculate latency for this batch
        var latencyMs = lastParsedTimestamp.HasValue 
            ? (DateTime.UtcNow - lastParsedTimestamp.Value).TotalMilliseconds 
            : 0.0;
        _statsObserver.Handler.AddLatency((long)latencyMs);

        return new BatchProcessResult(parsed, dropped, backpressure, latencyMs);
    }

    private async Task<bool> ForwardToParsedChannelAsync(T parsed, CancellationToken token)
    {
        // Try fast path first
        if (_parsedChannel.Writer.TryWrite(parsed))
        {
            _statsObserver.DbWriter.IncrementChannelCount();
            return false; // No backpressure
        }

        // Slow path - await write
        _statsObserver.Handler.IncrementBackpressure();
        await _parsedChannel.Writer.WriteAsync(parsed, token);
        _statsObserver.DbWriter.IncrementChannelCount();
        return true; // Had backpressure
    }

    private void RecordParseSuccess()
    {
        _statsObserver.Handler.IncrementParsed();
        _statsObserver.IncrementParseFor(_entityName, success: true);
    }

    private void RecordParseFailure()
    {
        _statsObserver.Handler.IncrementDropped();
        _statsObserver.IncrementParseFor(_entityName, success: false);
    }

    private void LogBatchStats(int workerId, BatchProcessResult result)
    {
        var totalCaptured = _statsObserver.Handler.GetCaptured();
        var totalParsed = _statsObserver.Handler.GetParsed();
        var totalDropped = _statsObserver.Handler.GetDropped();
        var totalBackpressure = _statsObserver.Handler.GetBackpressure();
        
        _logger.LogInformation(
            "[HANDLER-SERVICE] [PARSER] {Entity} Worker {Worker}: Batch=(Parsed:{BatchParsed} Dropped:{BatchDropped} BP:{BatchBP} Latency:{Latency:F1}ms) Total=(Captured:{TotalCaptured} Parsed:{TotalParsed} Dropped:{TotalDropped} BP:{TotalBP})",
            typeof(T).Name, workerId, result.Parsed, result.Dropped, result.Backpressure, result.LatencyMs, 
            totalCaptured, totalParsed, totalDropped, totalBackpressure);
    }

    #endregion

    #region Helper Methods

    private T? Parse(ReadOnlySpan<byte> raw)
    {
        if (raw.IsEmpty) return null;
        try { return _parseMapper.Map<T>(raw); }
        catch { return null; }
    }

    private string GetEntityName()
    {
        return typeof(T).Name switch
        {
            nameof(MotionPacketEntity) => Constants.MOTION_ENTITY_NAME,
            nameof(SafetyPacketEntity) => Constants.SAFETY_ENTITY_NAME,
            nameof(OnVIFPacketEntity) => Constants.ONVIF_ENTITY_NAME,
            _ => "Unknown"
        };
    }

    private string GetRawChannelName()
    {
        return typeof(T).Name switch
        {
            nameof(MotionPacketEntity) => Constants.MOTION_RAW_CHANNEL_NAME,
            nameof(SafetyPacketEntity) => Constants.SAFETY_RAW_CHANNEL_NAME,
            nameof(OnVIFPacketEntity) => Constants.ONVIF_RAW_CHANNEL_NAME,
            _ => "UnknownRaw"
        };
    }

    private EndpointSpecification[] GetEndpointsFromRangeConfig(BPFConfDto bpfConfig)
    {
        return typeof(T).Name switch
        {
            nameof(MotionPacketEntity) => bpfConfig.Motion ?? [],
            nameof(SafetyPacketEntity) => ToSafetyArray(bpfConfig.Safety),
            nameof(OnVIFPacketEntity) => bpfConfig.OnVIF ?? [],
            _ => []
        };
    }

    private EndpointSpecification[] GetEndpointsFromBpfConfig(BPFConfDto bpfConfig)
    {
        return typeof(T).Name switch
        {
            nameof(MotionPacketEntity) => bpfConfig.Motion ?? [],
            nameof(SafetyPacketEntity) => ToSafetyArray(bpfConfig.Safety),
            nameof(OnVIFPacketEntity) => bpfConfig.OnVIF ?? [],
            _ => []
        };
    }

    private static EndpointSpecification[] ToSafetyArray(BPFConfDto.SafetyConf? safety)
    {
        if (safety is null) return [];
        var list = new List<EndpointSpecification>(2);
        if (safety.Sbe is EndpointSpecification sbe)
            list.Add(new EndpointSpecification(sbe.IP, sbe.Port));
        if (safety.Pbe is EndpointSpecification pbe)
            list.Add(new EndpointSpecification(pbe.IP, pbe.Port));
        return [.. list];
    }

    private void UpdateRawChannelStats()
    {
        var channelCount = Interlocked.Read(ref _rawChannelCount);
        var utilization = (double)channelCount / _rawCapacity * 100;
        var avgLatency = _statsObserver.Handler.GetAverageLatency();
        var channelName = GetRawChannelName();
        _statsObserver.UpdateChannelStats(channelName, _rawCapacity, (int)channelCount, utilization, _workerCount, avgLatency);
    }

    #endregion

    #region IObservable<BasePacketEntity>

    public IDisposable Subscribe(IObserver<BasePacketEntity> observer)
    {
        ArgumentNullException.ThrowIfNull(observer);
        return new Unsubscriber<BasePacketEntity>([observer], observer);
    }

    #endregion

    private record BatchProcessResult(int Parsed, int Dropped, int Backpressure, double LatencyMs);
}
