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

public class HandlerService<T> : BackgroundService, IHandlerService<T> where T : BasePacketEntity
{
    private readonly ILogger<HandlerService<T>> _logger;
    private readonly StatsObserver _statsObserver;

    // Device filters
    private readonly string _protocol;
    private readonly IEnumerable<string> _ports;

    private readonly ITransmissionService? _transmissionService;

    // Channels
    private readonly Channel<RawPacketEvent> _rawChannel; // device -> handler
    private readonly Channel<T> _parsedChannel;           // handler -> DbWriter
    private readonly int _rawCapacity;

    private readonly int _workerCount;
    
    // Hub transmission
    private readonly TimeSpan _transmissionInterval;
    private readonly TimeSpan _batchTimeout;

    // Channel counts (manual tracking since bounded channels don't support Reader.Count)
    private long _rawChannelCount;
    
    // Auto-scaling
    private volatile int _currentWorkers;

    private const int RAW_READ_BURST = 128; // Smaller burst for lower latency

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
        _minWorkers = concurrency.GetValue<int>("MinWorkers", 2);
        _maxWorkers = concurrency.GetValue<int>("MaxWorkers", 8);
        _batchTimeout = TimeSpan.FromMilliseconds(concurrency.GetValue<int>("BatchTimeoutMs", 30));
        _workerCount = 4; // Default start with 4 workers
        
        _currentWorkers = _workerCount;
        
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
            endpoints = config.BpfConfig.Safety ?? [];
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
            endpoints = bpfConfig.Safety ?? [];
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
        var filter = BpfFilterBuilder.Build(_protocol, _ports);
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
        // Increment per-pipeline captured counters
        if (typeof(T) == typeof(MotionPacketEntity))
            _statsObserver.Handler.IncrementMotionCaptured();
        else if (typeof(T) == typeof(SafetyPacketEntity))
            _statsObserver.Handler.IncrementSafetyCaptured();
        else if (typeof(T) == typeof(OnVIFPacketEntity))
            _statsObserver.Handler.IncrementOnvifCaptured();
        
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
        // Dictionary to track all worker cancellation tokens (initial + dynamic)
        var workerCancellationTokens = new Dictionary<int, CancellationTokenSource>();
        var workerTasks = new Dictionary<int, Task>();

        // Push initial raw channel stats so capacity appears in telemetry immediately
        UpdateRawChannelStats();

        // Start initial workers with individual cancellation tokens
        var workers = new List<Task>();
        for (int i = 0; i < _workerCount; i++)
        {
            int workerId = i;
            var workerCts = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
            workerCancellationTokens[workerId] = workerCts;
            
            var task = Task.Factory.StartNew(
                () => WorkerLoopAsync(workerId, workerCts.Token),
                workerCts.Token,
                TaskCreationOptions.LongRunning,
                TaskScheduler.Default).Unwrap();

            workers.Add(task);
            workerTasks[workerId] = task;
        }
        
        // Start auto-scaler
        var autoScalerTask = Task.Factory.StartNew(
            () => AutoScalerAsync(stoppingToken, workers, workerCancellationTokens, workerTasks), // CHANGED
            stoppingToken,
            TaskCreationOptions.LongRunning,
            TaskScheduler.Default).Unwrap();

        return Task.WhenAll(workers.Concat(new[] { autoScalerTask }));
    }

    private async Task AutoScalerAsync(
        CancellationToken stoppingToken,
        List<Task> workers,
        Dictionary<int, CancellationTokenSource> workerCancellationTokens,
        Dictionary<int, Task> workerTasks)
    {
        var checkInterval = TimeSpan.FromSeconds(10);      // sampling cadence
        using var timer = new PeriodicTimer(checkInterval);

        // Windows you requested
        var scaleUpWindow   = TimeSpan.FromSeconds(30);
        var scaleDownWindow = TimeSpan.FromMinutes(1);

        // Cooldowns equal to the windows, per your rule
        var scaleUpCooldown   = scaleUpWindow;
        var scaleDownCooldown = scaleDownWindow;

        // Elapsed trackers
        TimeSpan highLatencyElapsed = TimeSpan.Zero;
        TimeSpan lowLatencyElapsed  = TimeSpan.Zero;

        // Last scale action time (to enforce cooldown)
        DateTime? lastScaleAt = null;

        // Target latency is batch timeout (your rule)
        double targetMs = _batchTimeout.TotalMilliseconds;

        // Next allowed time to make any scaling decision (enforced cooldown)
        DateTime nextDecisionNotBefore = DateTime.UtcNow;

        int nextWorkerId = workerCancellationTokens.Count; // continue ids after initial set

        try
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                await timer.WaitForNextTickAsync(stoppingToken);

                // Enforce cooldown after any scale action
                if (DateTime.UtcNow < nextDecisionNotBefore)
                {
                    _logger.LogDebug("[AUTO-SCALER] Cooling down until {Until:o}", nextDecisionNotBefore);
                    continue;
                }

                var currentLatency = _statsObserver.Handler.GetAverageLatency();
                var currentWorkers = _currentWorkers;

                // Update elapsed windows
                if (currentLatency > targetMs)
                {
                    highLatencyElapsed += checkInterval;
                    lowLatencyElapsed = TimeSpan.Zero;
                }
                else if (currentLatency > 0) // treat 0 as "no signal yet"
                {
                    lowLatencyElapsed += checkInterval;
                    highLatencyElapsed = TimeSpan.Zero;
                }
                else
                {
                    // No samples; don't accumulate either window
                    highLatencyElapsed = TimeSpan.Zero;
                    lowLatencyElapsed  = TimeSpan.Zero;
                }

                _logger.LogDebug(
                    "[AUTO-SCALER] {Entity} Workers={Workers} Latency={Latency:F1}ms Target={Target:F1}ms | HighElapsed={High}s LowElapsed={Low}s",
                    typeof(T).Name, currentWorkers, currentLatency, targetMs,
                    (int)highLatencyElapsed.TotalSeconds, (int)lowLatencyElapsed.TotalSeconds);

                // --- SCALE UP ---
                if (currentLatency > targetMs &&
                    currentWorkers < _maxWorkers &&
                    highLatencyElapsed >= scaleUpWindow)
                {
                    int newWorkers = currentWorkers + 1;
                    _currentWorkers = newWorkers;

                    int workerId = nextWorkerId++;
                    var workerCts = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
                    workerCancellationTokens[workerId] = workerCts;

                    _logger.LogInformation(
                        "[AUTO-SCALER] {Entity} SCALING UP: {Old} -> {New} (latency {Latency:F1}ms > target {Target:F1}ms for {Window}s)",
                        typeof(T).Name, currentWorkers, newWorkers, currentLatency, targetMs, (int)scaleUpWindow.TotalSeconds);

                    var task = Task.Factory.StartNew(
                        () => WorkerLoopAsync(workerId, workerCts.Token),
                        workerCts.Token,
                        TaskCreationOptions.LongRunning,
                        TaskScheduler.Default).Unwrap();

                    workers.Add(task);
                    workerTasks[workerId] = task;

                    // reset window and set cooldown
                    highLatencyElapsed = TimeSpan.Zero;
                    lastScaleAt = DateTime.UtcNow;
                    nextDecisionNotBefore = lastScaleAt.Value + scaleUpCooldown;
                    continue; // skip further checks this tick
                }

                // --- SCALE DOWN ---
                if (currentLatency > 0 &&
                    currentLatency <= targetMs &&
                    currentWorkers > _minWorkers &&
                    lowLatencyElapsed >= scaleDownWindow)
                {
                    int newWorkers = currentWorkers - 1;
                    _currentWorkers = newWorkers;

                    // choose the highest id to terminate
                    var workerToTerminate = workerCancellationTokens.Keys.Max();

                    _logger.LogInformation(
                        "[AUTO-SCALER] {Entity} SCALING DOWN: {Old} -> {New} (latency {Latency:F1}ms ≤ target {Target:F1}ms for {Window}s)",
                        typeof(T).Name, currentWorkers, newWorkers, currentLatency, targetMs, (int)scaleDownWindow.TotalSeconds);

                    if (workerCancellationTokens.TryGetValue(workerToTerminate, out var cts))
                    {
                        // signal graceful stop; worker will flush then exit
                        cts.Cancel();

                        // Await the task to ensure it "finishes" before we proceed
                        if (workerTasks.TryGetValue(workerToTerminate, out var wt))
                        {
                            try { await wt; } catch (OperationCanceledException) { } catch { /* already logged in worker */ }
                            workerTasks.Remove(workerToTerminate);
                            workers.Remove(wt);
                        }

                        cts.Dispose();
                        workerCancellationTokens.Remove(workerToTerminate);

                        _logger.LogInformation(
                            "[AUTO-SCALER] {Entity} Worker {WorkerId} terminated gracefully (remaining {Remaining})",
                            typeof(T).Name, workerToTerminate, newWorkers);
                    }

                    // reset window and set cooldown
                    lowLatencyElapsed = TimeSpan.Zero;
                    lastScaleAt = DateTime.UtcNow;
                    nextDecisionNotBefore = lastScaleAt.Value + scaleDownCooldown;
                    continue; // skip further checks this tick
                }
            }
        }
        catch (OperationCanceledException) { /* normal on shutdown */ }
        finally
        {
            // ensure all pending cancels get disposed by caller
        }
    }

    private async Task WorkerLoopAsync(int workerId, CancellationToken token)
    {
        // Pre-allocate scope dictionary to avoid repeated allocations
        var scopeState = new Dictionary<string, object>(2)
        {
            ["Worker"] = workerId,
            ["Entity"] = typeof(T).Name
        };
        using var scope = _logger.BeginScope(scopeState);

        // Rent arrays from pool - allocate once, reuse throughout worker lifetime
        var rawBatch = ArrayPool<RawPacketEvent>.Shared.Rent(RAW_READ_BURST);
        var parsedBatch = ArrayPool<T>.Shared.Rent(RAW_READ_BURST);
        
        long batchNumber = 0;
        DateTime? oldestInBufferUtc = null;
        int rawCount = 0;
        int parsedCount = 0;
        
        using var timer = new PeriodicTimer(_batchTimeout);
        Task<bool> tickTask = timer.WaitForNextTickAsync(token).AsTask();

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

    private async Task<int> FlushBatchInternal(IReadOnlyList<T> parsedBatch, int workerId, long batchNumber, CancellationToken token)
    {
        if (parsedBatch.Count == 0) return 0;

        var backpressureCount = 0;

        for (int i = 0; i < parsedBatch.Count; i++)
        {
            var parsed = parsedBatch[i];

            // Send to transmission service (fire and forget)
            _transmissionService?.OnNext(parsed);
            
            // Write to parsed channel (can block if full - this is the bottleneck for DB writer)
            if (!_parsedChannel.Writer.TryWrite(parsed))
            {
                _statsObserver.Handler.IncrementBackpressure();
                backpressureCount++;
                await _parsedChannel.Writer.WriteAsync(parsed, token);
                // Successfully enqueued after waiting; reflect in parsed-channel count
                _statsObserver.DbWriter.IncrementChannelCount();
            }
            else
            {
                // Successfully enqueued immediately; reflect in parsed-channel count
                _statsObserver.DbWriter.IncrementChannelCount();
            }
        }

        return backpressureCount;
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
        
        _statsObserver.UpdateChannelStats(channelName, rawCapacity, (int)rawChannelCount, rawUtilization, _currentWorkers);
    }
}
