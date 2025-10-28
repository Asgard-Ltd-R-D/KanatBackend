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
namespace PacketProcessing.Services.Realtime.Networking;

public class HandlerService<T> : BackgroundService, IHandlerService<T> where T : BasePacketEntity
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

    private int _workerCount;
    private readonly int _minWorkers;
    private readonly int _maxWorkers;
    
    // Hub transmission
    private readonly TimeSpan _transmissionInterval;
    private readonly TimeSpan _batchTimeout;

    // Channel counts (manual tracking since bounded channels don't support Reader.Count)
    private long _rawChannelCount;
    
    // Auto-scaling
    private volatile int _currentWorkers;
    private readonly CancellationTokenSource _workersCancellation = new();

    private const int RAW_READ_BURST = 64; // Smaller burst for lower latency

    private IDisposable? _subscription;

    private readonly ParseMapper _parseMapper;

    public HandlerService(
        string dataPipeName,
        ITransmissionService transmissionService,
        ILogger<HandlerService<T>> logger,
        Channel<T> parsedChannel,
        IConfiguration configuration,
        ParseMapper parseMapper,
        StatsObserver statsObserver)
    {
        _logger = logger;
        _parsedChannel = parsedChannel;
        _transmissionService = transmissionService;
        _parseMapper = parseMapper;
        _statsObserver = statsObserver;
        
        // bounded channel for raw events with increased capacity
        // Wait mode ensures no packets are dropped (capture may block if processing too slow)
        _rawChannel = Channel.CreateBounded<RawPacketEvent>(
            new BoundedChannelOptions(500_000) { 
                SingleReader = false,  // Multiple workers read
                SingleWriter = false,  // DeviceService may write from multiple threads via Task.Run
                FullMode = BoundedChannelFullMode.Wait  // Block to guarantee delivery
            });

        _protocol = configuration.GetValue<string>($"{dataPipeName}:Network:Protocol") ?? "";
        _ips = configuration.GetSection($"{dataPipeName}:Network:IPs").Get<IEnumerable<string>>() ?? [];

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
            "[HANDLER-SERVICE] {Handler} initialized with {Workers} workers (RawChannelCapacity:500K, ParsedChannelCapacity:{ParsedCap}, every {IntervalMs}ms",
            typeof(T).Name, _workerCount, parsedChannel.Reader.CanCount ? "?" : "Bounded", _transmissionInterval.TotalMilliseconds);
    }

    #region IHandlerService

    public async Task SubscribeToDeviceAsync(IDeviceService deviceService, string deviceName)
    {
        var filter = BpfFilterBuilder.Build(_protocol, _ips);
        await deviceService.SubscribeWithFilterAsync(this, deviceName, filter);
        _logger.LogInformation("{Handler} subscribed to {Device} with filter {Filter}",
            typeof(T).Name, deviceName, filter);
    }

    public async Task UnsubscribeAsync(IDeviceService deviceService)
    {
        _subscription?.Dispose();
        _subscription = null;
        await deviceService.UnsubscribeAsync(this);

        _statsObserver.Handler.Reset();
        Interlocked.Exchange(ref _rawChannelCount, 0);

        _logger.LogInformation("{Handler} unsubscribed", typeof(T).Name);
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
        
        _logger.LogInformation("{Handler} statistics reset", typeof(T).Name);
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
            
            // Update channel stats after incrementing
            var currentCount = Interlocked.Read(ref _rawChannelCount);
            var utilization = (double)currentCount / 500_000 * 100;
            
            if (typeof(T) == typeof(PacketProcessing.Entities.Packet.MotionPacketEntity))
                _statsObserver.UpdateChannelStats("MotionRaw", 500_000, (int)currentCount, utilization, _currentWorkers);
            else if (typeof(T) == typeof(PacketProcessing.Entities.Packet.SafetyPacketEntity))
                _statsObserver.UpdateChannelStats("SafetyRaw", 500_000, (int)currentCount, utilization, _currentWorkers);
            else if (typeof(T) == typeof(PacketProcessing.Entities.Packet.OnVIFPacketEntity))
                _statsObserver.UpdateChannelStats("OnvifRaw", 500_000, (int)currentCount, utilization, _currentWorkers);
            
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
        
        // Update channel stats after incrementing
        var finalCount = Interlocked.Read(ref _rawChannelCount);
        var finalUtilization = (double)finalCount / 500_000 * 100;
        
        if (typeof(T) == typeof(PacketProcessing.Entities.Packet.MotionPacketEntity))
            _statsObserver.UpdateChannelStats("MotionRaw", 500_000, (int)finalCount, finalUtilization, _currentWorkers);
        else if (typeof(T) == typeof(PacketProcessing.Entities.Packet.SafetyPacketEntity))
            _statsObserver.UpdateChannelStats("SafetyRaw", 500_000, (int)finalCount, finalUtilization, _currentWorkers);
        else if (typeof(T) == typeof(PacketProcessing.Entities.Packet.OnVIFPacketEntity))
            _statsObserver.UpdateChannelStats("OnvifRaw", 500_000, (int)finalCount, finalUtilization, _currentWorkers);
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
        
        // Start initial workers with individual cancellation tokens
        var workers = new List<Task>();
        for (int i = 0; i < _workerCount; i++)
        {
            int workerId = i;
            var workerCts = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
            workerCancellationTokens[workerId] = workerCts;
            
            workers.Add(Task.Factory.StartNew(
                () => WorkerLoopAsync(workerId, workerCts.Token),
                workerCts.Token,
                TaskCreationOptions.LongRunning,
                TaskScheduler.Default).Unwrap());
        }
        
        // Start auto-scaler
        var autoScalerTask = Task.Factory.StartNew(
            () => AutoScalerAsync(stoppingToken, workers, workerCancellationTokens),
            stoppingToken,
            TaskCreationOptions.LongRunning,
            TaskScheduler.Default).Unwrap();

        return Task.WhenAll(workers.Concat([autoScalerTask]));
    }
    
    private async Task AutoScalerAsync(CancellationToken stoppingToken, List<Task> workers, Dictionary<int, CancellationTokenSource> workerCancellationTokens)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(10)); // Check every 10 seconds
        const double TARGET_LATENCY_MS = 30.0; // Fixed target latency
        var scalingHighLatencyCount = 0;
        var scalingLowLatencyCount = 0;
        int nextWorkerId = _workerCount;
        
        try
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                await timer.WaitForNextTickAsync(stoppingToken);
                
                var currentLatency = _statsObserver.Handler.GetAverageLatency();
                var currentWorkers = _currentWorkers;
                
                // Scale UP: If latency > 30ms for 30 seconds, add workers until latency ≤ 30ms or max workers reached
                if (currentLatency > TARGET_LATENCY_MS && currentWorkers < _maxWorkers)
                {
                    scalingHighLatencyCount++;
                    
                    // Scale up if condition persists for 30 seconds (3 checks)
                    if (scalingHighLatencyCount >= 3)
                    {
                        var newWorkers = currentWorkers + 1;
                        _logger.LogInformation(
                            "[AUTO-SCALER] {Entity} SCALING UP: Increasing workers from {Old} to {New} (latency: {Current:F1}ms > {Target:F1}ms)",
                            typeof(T).Name, currentWorkers, newWorkers, currentLatency, TARGET_LATENCY_MS);
                        
                        _currentWorkers = newWorkers;
                        
                        // Start a new worker with its own cancellation token
                        int workerId = nextWorkerId++;
                        var workerCts = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
                        workerCancellationTokens[workerId] = workerCts;
                        
                        _logger.LogInformation(
                            "[AUTO-SCALER] {Entity} Starting new worker {WorkerId} (total workers: {TotalWorkers})",
                            typeof(T).Name, workerId, newWorkers);
                        
                        workers.Add(Task.Factory.StartNew(
                            () => WorkerLoopAsync(workerId, workerCts.Token),
                            workerCts.Token,
                            TaskCreationOptions.LongRunning,
                            TaskScheduler.Default).Unwrap());
                        
                        // Reset counter
                        scalingHighLatencyCount = 0;
                    }
                }
                else
                {
                    scalingHighLatencyCount = 0;
                }
                
                // Scale DOWN: If latency ≤ 30ms for 1 minute (60 seconds), remove workers until latency > 30ms or min workers reached
                if (currentLatency > 0 && currentLatency <= TARGET_LATENCY_MS && currentWorkers > _minWorkers)
                {
                    scalingLowLatencyCount++;
                    
                    // Wait 1 minute (6 checks) before scaling down
                    if (scalingLowLatencyCount >= 6)
                    {
                        var newWorkers = currentWorkers - 1;
                        _logger.LogInformation(
                            "[AUTO-SCALER] {Entity} SCALING DOWN: Decreasing workers from {Old} to {New} (latency: {Current:F1}ms ≤ {Target:F1}ms for 1 minute)",
                            typeof(T).Name, currentWorkers, newWorkers, currentLatency, TARGET_LATENCY_MS);
                        
                        _currentWorkers = newWorkers;
                        
                        // Find and terminate the last worker
                        var workerToTerminate = workerCancellationTokens.Keys.Max();
                        if (workerCancellationTokens.TryGetValue(workerToTerminate, out var cts))
                        {
                            cts.Cancel();
                            workerCancellationTokens.Remove(workerToTerminate);
                            _logger.LogInformation(
                                "[AUTO-SCALER] {Entity} Terminated worker {WorkerId} (remaining workers: {RemainingWorkers})",
                                typeof(T).Name, workerToTerminate, newWorkers);
                        }
                        
                        // Reset counter
                        scalingLowLatencyCount = 0;
                    }
                }
                else
                {
                    scalingLowLatencyCount = 0;
                }
                
                // Log status every check
                _logger.LogDebug(
                    "[AUTO-SCALER] {Entity} Workers={Workers} Latency={Latency:F1}ms Target={Target:F1}ms (HighCount={HighCount} LowCount={LowCount})",
                    typeof(T).Name, currentWorkers, currentLatency, TARGET_LATENCY_MS, scalingHighLatencyCount, scalingLowLatencyCount);
            }
        }
        catch (OperationCanceledException) { }
        finally
        {
            // Clean up all worker cancellation tokens
            foreach (var cts in workerCancellationTokens.Values)
            {
                cts.Cancel();
                cts.Dispose();
            }
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
                var dataAvailableTask = _rawChannel.Reader.WaitToReadAsync(token).AsTask();
                var completed = await Task.WhenAny(dataAvailableTask, tickTask);

                if (completed == dataAvailableTask)
                {
                    // Channel signaled; may be false if completed
                    if (dataAvailableTask.Result)
                    {
                        // Aggressive draining: Read first item, then drain as many as possible
                        if (_rawChannel.Reader.TryRead(out var firstItem))
                        {
                            rawBatch[rawCount] = firstItem;
                            rawCount++;
                            Interlocked.Decrement(ref _rawChannelCount);

                            // Track oldest timestamp for latency measurement
                            if (!oldestInBufferUtc.HasValue || firstItem.Timestamp < oldestInBufferUtc.Value)
                                oldestInBufferUtc = firstItem.Timestamp;

                            // Drain remaining items without blocking (optimized)
                            while (rawCount < RAW_READ_BURST && _rawChannel.Reader.TryRead(out var more))
                            {
                                rawBatch[rawCount] = more;
                                rawCount++;
                                Interlocked.Decrement(ref _rawChannelCount);

                                if (!oldestInBufferUtc.HasValue || more.Timestamp < oldestInBufferUtc.Value)
                                    oldestInBufferUtc = more.Timestamp;
                            }
                        }
                        
                        // Parse raw batch into parsed batch
                        for (int i = 0; i < rawCount; i++)
                        {
                            var raw = rawBatch[i];
                            ArraySegment<byte> segment = default;
                            
                            try
                            {
                                var parsed = Parse(raw.Data.Span);
                                
                                if (parsed is null)
                                {
                                    _statsObserver.Handler.IncrementDropped();
                                    if (MemoryMarshal.TryGetArray(raw.Data, out segment) && segment.Array is not null)
                                        ArrayPool<byte>.Shared.Return(segment.Array);
                                    continue;
                                }

                                parsed.Timestamp = raw.Timestamp;

                                if (MemoryMarshal.TryGetArray(raw.Data, out segment) && segment.Array is not null)
                                    ArrayPool<byte>.Shared.Return(segment.Array);

                                parsedBatch[parsedCount] = parsed;
                                parsedCount++;
                                _statsObserver.Handler.IncrementParsed();
                            }
                            catch
                            {
                                _statsObserver.Handler.IncrementDropped();
                                if (MemoryMarshal.TryGetArray(raw.Data, out segment) && segment.Array is not null)
                                    ArrayPool<byte>.Shared.Return(segment.Array);
                            }
                        }
                        
                        rawCount = 0; // Reset raw count
                        
                        // Check if we should flush (batch full OR timeout reached)
                        var shouldFlush = parsedCount >= RAW_READ_BURST ||
                            (parsedCount > 0 && oldestInBufferUtc.HasValue &&
                                (DateTime.UtcNow - oldestInBufferUtc.Value) >= _transmissionInterval);
                        
                        if (shouldFlush)
                        {
                            var segment = new ArraySegment<T>(parsedBatch, 0, parsedCount);
                            batchNumber++;
                            
                            // Calculate latency from oldest packet in batch
                            var oldest = oldestInBufferUtc ?? DateTime.UtcNow;
                            var processingLatencyMs = (DateTime.UtcNow - oldest).TotalMilliseconds;
                            
                            // Track latency for auto-scaler
                            _statsObserver.Handler.AddLatency((long)processingLatencyMs);
                            
                            // Track per-channel latency
                            var channelName = typeof(T).Name switch
                            {
                                nameof(MotionPacketEntity) => "MotionRaw",
                                nameof(SafetyPacketEntity) => "SafetyRaw",
                                nameof(OnVIFPacketEntity) => "OnvifRaw",
                                _ => "UnknownRaw"
                            };
                            _statsObserver.AddChannelLatency(channelName, processingLatencyMs);
                            
                            var backpressureCount = await FlushBatchInternal(segment, workerId, batchNumber, token);
                            
                            _logger.LogInformation(
                                "[PARSER] {Entity} Worker {Worker} Batch #{Batch}: Parsed={Parsed} Latency={Latency:F1}ms BP={Backpressure} | Total Captured={Captured} Parsed={TotalParsed} Dropped={TotalDropped} BP={TotalBP}",
                                typeof(T).Name, workerId, batchNumber, parsedCount, processingLatencyMs, backpressureCount,
                                _statsObserver.Handler.GetCaptured(), _statsObserver.Handler.GetParsed(),
                                _statsObserver.Handler.GetDropped(), _statsObserver.Handler.GetBackpressure());
                            
                            parsedCount = 0;
                            oldestInBufferUtc = null;
                        }
                    }
                    else
                    {
                        // Channel completed
                        break;
                    }
                }
                else // Timer tick fired
                {
                    var ticked = await tickTask;
                    if (!ticked) break;

                    // Flush on timer if anything pending
                    if (parsedCount > 0)
                    {
                        var segment = new ArraySegment<T>(parsedBatch, 0, parsedCount);
                        batchNumber++;
                        
                        // Calculate latency from oldest packet in batch
                        var oldest = oldestInBufferUtc ?? DateTime.UtcNow;
                        var processingLatencyMs = (DateTime.UtcNow - oldest).TotalMilliseconds;
                        
                        // Track latency for auto-scaler
                        _statsObserver.Handler.AddLatency((long)processingLatencyMs);
                        
                        // Track per-channel latency
                        var channelName = typeof(T).Name switch
                        {
                            nameof(MotionPacketEntity) => "MotionRaw",
                            nameof(SafetyPacketEntity) => "SafetyRaw",
                            nameof(OnVIFPacketEntity) => "OnvifRaw",
                            _ => "UnknownRaw"
                        };
                        _statsObserver.AddChannelLatency(channelName, processingLatencyMs);
                        
                        var backpressureCount = await FlushBatchInternal(segment, workerId, batchNumber, token);
                        
                        _logger.LogInformation(
                            "[PARSER] {Entity} Worker {Worker} Batch #{Batch}: Parsed={Parsed} Latency={Latency:F1}ms BP={Backpressure} | Total Captured={Captured} Parsed={TotalParsed} Dropped={TotalDropped} BP={TotalBP}",
                            typeof(T).Name, workerId, batchNumber, parsedCount, processingLatencyMs, backpressureCount,
                            _statsObserver.Handler.GetCaptured(), _statsObserver.Handler.GetParsed(),
                            _statsObserver.Handler.GetDropped(), _statsObserver.Handler.GetBackpressure());
                        
                        parsedCount = 0;
                        oldestInBufferUtc = null;
                    }
                    
                    // Start next tick wait
                    tickTask = timer.WaitForNextTickAsync(token).AsTask();
                }
            }
        }
        catch (ChannelClosedException)
        {
            // Final drain after close
            if (parsedCount > 0)
            {
                var segment = new ArraySegment<T>(parsedBatch, 0, parsedCount);
                batchNumber++;
                var backpressureCount = await FlushBatchInternal(segment, workerId, batchNumber, token);
                
                _logger.LogInformation(
                    "[PARSER] {Entity} Worker {Worker} Channel Close Batch #{Batch}: Parsed={Parsed} BP={Backpressure}",
                    typeof(T).Name, workerId, batchNumber, parsedCount, backpressureCount);
            }
        }
        catch (OperationCanceledException)
        {
            // Shutdown requested — final flush
            if (parsedCount > 0)
            {
                var segment = new ArraySegment<T>(parsedBatch, 0, parsedCount);
                batchNumber++;
                var backpressureCount = await FlushBatchInternal(segment, workerId, batchNumber, token);
                
                _logger.LogInformation(
                    "[PARSER] {Entity} Worker {Worker} Final Batch #{Batch}: Parsed={Parsed} BP={Backpressure}",
                    typeof(T).Name, workerId, batchNumber, parsedCount, backpressureCount);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[{Entity}] Worker {Worker} crashed", typeof(T).Name, workerId);
            throw;
        }
        finally
        {
            UpdateRawChannelStats();
            
            // Return arrays to pool
            ArrayPool<RawPacketEvent>.Shared.Return(rawBatch);
            ArrayPool<T>.Shared.Return(parsedBatch);
        }
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
        var rawCapacity = 500_000; // Hardcoded capacity from channel creation
        var rawUtilization = (double)rawChannelCount / rawCapacity * 100;
        
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
