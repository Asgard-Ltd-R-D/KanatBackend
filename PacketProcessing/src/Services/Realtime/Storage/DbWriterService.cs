using System.Buffers;
using System.Net.Sockets;
using System.Threading.Channels;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using PacketProcessing.Entities;
using PacketProcessing.Repositories.InfluxRepository;
using QuestDB.Senders;
using QuestDB;
using Microsoft.Extensions.Configuration;
using PacketProcessing.Config;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Utils.Observers;

namespace PacketProcessing.Services.Realtime.Storage;

/// <summary>
/// Dedicated service that consumes from channel and flushes batches into QuestDB.
/// </summary>
public class DbWriterService<T> : BackgroundService, IDbWriterService<T> where T : BasePacketEntity
{
    private readonly ILogger<DbWriterService<T>> _logger;
    private readonly Channel<T> _channel;
    private readonly IInfluxRepository<T> _repository;
    private readonly string _connectionString;
    private readonly int _batchSize;
    private readonly TimeSpan _batchTimeout;
    private int _workerCount;
    private readonly int _minWorkers;
    private readonly int _maxWorkers;
    private readonly StatsObserver _statsObserver;
    
    // Auto-scaling
    private volatile int _currentWorkers;

    public DbWriterService(
        ILogger<DbWriterService<T>> logger,
        Channel<T> channel,
        IInfluxRepository<T> repository,
        IOptions<QuestDbConfiguration> options,
        IConfiguration configuration,
        StatsObserver statsObserver)
    {
        _logger = logger;
        _channel = channel;
        _repository = repository;
        _statsObserver = statsObserver;

        var concurrency = configuration.GetSection("Concurrency");
        _batchSize = concurrency.GetValue<int>("BatchSize", 1000);
        _batchTimeout = TimeSpan.FromMilliseconds(concurrency.GetValue<int>("BatchTimeoutMs", 30));

        _minWorkers = concurrency.GetValue<int>("MinWorkers", 2);
        _maxWorkers = concurrency.GetValue<int>("MaxWorkers", 8);
        _workerCount = 4; // Default start with 4 workers
        _currentWorkers = _workerCount;

        var opt = options.Value;
        // Optimize connection string for high-throughput ingestion
        _connectionString =
            $"http::addr={opt.Host}:{opt.InfluxPort};" +
            $"username={opt.Username};password={opt.Password};" +
            $"request_min_throughput=500000;" +  // Target 500K packets/sec throughput
            $"request_timeout=5000;" +            // 5 second timeout for requests
            $"retry_timeout=1000;";
        
        _logger.LogInformation(
            "[DB-WRITER] {Entity} initialized with {Workers} workers, BatchSize={BatchSize}, Timeout={Timeout}ms",
            typeof(T).Name, _workerCount, _batchSize, _batchTimeout.TotalMilliseconds);
    }

    // ----------- BackgroundService entry point -----------
    protected override Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("[DB-WRITER] {Entity} Starting {Workers} worker loops...", typeof(T).Name, _workerCount);
        
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

        _logger.LogInformation("[DB-WRITER] {Entity} All {Workers} workers started", typeof(T).Name, _workerCount);
        
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
                
                var currentLatency = _statsObserver.DbWriter.GetAverageLatency();
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
    
        ISender? sender = null;
        
        // Rent array from pool - allocate once, reuse throughout worker lifetime
        var rentedArray = ArrayPool<T>.Shared.Rent(_batchSize);
        int bufferCount = 0;
        DateTime? oldestInBufferUtc = null;
        long batchNumber = 0; // Track batch number for each worker

        using var timer = new PeriodicTimer(_batchTimeout);
        Task<bool> tickTask = timer.WaitForNextTickAsync(token).AsTask(); // single, reusable tick task

        try
        {
            sender = Sender.New(_connectionString);

            while (!token.IsCancellationRequested) 
            {
                var dataAvailableTask = _channel.Reader.WaitToReadAsync(token).AsTask();

                var completed = await Task.WhenAny(dataAvailableTask, tickTask);

                if (completed == dataAvailableTask)
                {
                    // Channel signaled; may be false if completed
                    if (dataAvailableTask.Result) 
                    {
                        // Aggressive draining: Read first item, then drain as many as possible
                        if (_channel.Reader.TryRead(out var firstItem))
                        {
                            rentedArray[bufferCount] = firstItem;
                            bufferCount++;
                            
                            // Track oldest timestamp for latency measurement
                            if (!oldestInBufferUtc.HasValue || firstItem.Timestamp < oldestInBufferUtc.Value)
                                oldestInBufferUtc = firstItem.Timestamp;
                            
                            // Drain remaining items without blocking (optimized)
                            while (bufferCount < _batchSize && _channel.Reader.TryRead(out var more))
                            {
                                rentedArray[bufferCount] = more;
                                bufferCount++;
                                
                                if (!oldestInBufferUtc.HasValue || more.Timestamp < oldestInBufferUtc.Value)
                                    oldestInBufferUtc = more.Timestamp;
                            }
                        }
                        
                        // Update channel count (items moved to buffer)
                        _statsObserver.DbWriter.AddChannelCount(-bufferCount);

                        // Check if we should flush (batch full OR timeout reached)
                        var shouldFlush = bufferCount >= _batchSize ||
                            (bufferCount > 0 && oldestInBufferUtc.HasValue &&
                                (DateTime.UtcNow - oldestInBufferUtc.Value) >= _batchTimeout);
                            
                        if (shouldFlush)
                        {
                            var segment = new ArraySegment<T>(rentedArray, 0, bufferCount);
                            batchNumber++;
                            
                            // Flush to DB (this can block if database is slow)
                            await FlushBatchInternal(sender, segment, workerId, oldestInBufferUtc, batchNumber, token);
                            
                            bufferCount = 0;
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
                    if (bufferCount > 0)
                    {
                        var segment = new ArraySegment<T>(rentedArray, 0, bufferCount);
                        batchNumber++;
                        
                        await FlushBatchInternal(sender, segment, workerId, oldestInBufferUtc, batchNumber, token);
                        
                        bufferCount = 0;
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
            if (bufferCount > 0 && sender is not null)
            {
                var segment = new ArraySegment<T>(rentedArray, 0, bufferCount);
                batchNumber++;
                await FlushBatchInternal(sender, segment, workerId, oldestInBufferUtc, batchNumber, token);
                bufferCount = 0;
            }
        }
        catch (OperationCanceledException)
        {
            // Shutdown requested — final flush
            if (bufferCount > 0 && sender is not null)
            {
                var segment = new ArraySegment<T>(rentedArray, 0, bufferCount);
                batchNumber++;
                await FlushBatchInternal(sender, segment, workerId, oldestInBufferUtc, batchNumber, token);
                bufferCount = 0;
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[{Entity}] Worker {Worker} crashed", typeof(T).Name, workerId);
            throw;
        }
        finally
        {
            sender?.Dispose();
            
            // Return rented array to pool if we used it
            if (rentedArray != null)
            {
                ArrayPool<T>.Shared.Return(rentedArray, clearArray: false);
            }
        }
    }

    public (long Flushed, long Failed, double AvgLatencyMs) GetStats()
    {
        return (_statsObserver.DbWriter.GetFlushed(), 
                _statsObserver.DbWriter.GetFailed(), 
                _statsObserver.DbWriter.GetAverageLatency());
    }
    
    public int GetChannelCount()
    {
        // Channel count is calculated externally as (parsed - flushed)
        // This method exists for interface compliance but isn't directly used
        return 0;
    }
    
    public void ResetStats()
    {
        _statsObserver.DbWriter.Reset();
        
        _logger.LogInformation("[DB-WRITER] {Entity} statistics reset", typeof(T).Name);
    }

    // ----------- Internal logic -----------
    private async Task FlushBatchInternal(ISender sender, IReadOnlyList<T> batch, int workerId, DateTime? oldestInBufferUtc, long batchNumber, CancellationToken ct)
    {
        if (batch.Count == 0) return;
        
        var batchSize = batch.Count;
        var oldest = oldestInBufferUtc ?? DateTime.UtcNow;
        var writeStartTime = DateTime.UtcNow;
        var dbWriteLatencyMs = 0.0;
        var channelCount = _statsObserver.DbWriter.GetChannelCount();

        try
        {
            await _repository.WriteBatchQuestDbAsync(sender, batch, ct);
            var writeEndTime = DateTime.UtcNow;
            dbWriteLatencyMs = (writeEndTime - oldest).TotalMilliseconds; // Time from oldest packet to write completion
            
            _statsObserver.DbWriter.AddFlushed(batch.Count);
            _statsObserver.DbWriter.AddParsed(batch.Count); // Increment parsed count when actually written to DB
            
            // Track DB write latency (actual database write time)
            _statsObserver.DbWriter.AddLatency((long)dbWriteLatencyMs);
            
            // Track per-channel latency for parsed channels
            var channelName = typeof(T).Name switch
            {
                nameof(MotionPacketEntity) => "MotionParsed",
                nameof(SafetyPacketEntity) => "SafetyParsed",
                nameof(OnVIFPacketEntity) => "OnvifParsed",
                _ => "UnknownParsed"
            };
            _statsObserver.AddChannelLatency(channelName, dbWriteLatencyMs);
            
            var stats = GetStats();
            _logger.LogInformation(
                "[DB-WRITER] {Entity} Worker {Worker} Batch #{Batch}: Size={BatchSize} Latency={Latency:F1}ms Channel={Channel} | Total Flushed={TotalFlushed} Failed={TotalFailed} AvgLatency={AvgLatency:F1}ms",
                typeof(T).Name, workerId, batchNumber, batchSize, dbWriteLatencyMs, channelCount, stats.Flushed, stats.Failed, stats.AvgLatencyMs);
        }
        catch (Exception ex) when (ex is IOException || ex is SocketException || ex.GetType().Name.Contains("Ingress"))
        {
            _logger.LogWarning(ex, "ILP write failed, recreating sender and retrying...");
            sender.Dispose();
            sender = Sender.New(_connectionString);
            try
            {
                await _repository.WriteBatchQuestDbAsync(sender, batch, ct);
                var writeEndTime = DateTime.UtcNow;
                dbWriteLatencyMs = (writeEndTime - oldest).TotalMilliseconds; // Time from oldest packet to write completion
                
                _statsObserver.DbWriter.AddFlushed(batch.Count);
                _statsObserver.DbWriter.AddParsed(batch.Count); // Increment parsed count when actually written to DB
                
                // Track DB write latency (actual database write time)
                _statsObserver.DbWriter.AddLatency((long)dbWriteLatencyMs);

                // Track per-channel latency for parsed channels
                var channelName = typeof(T).Name switch
                {
                    nameof(MotionPacketEntity) => "MotionParsed",
                    nameof(SafetyPacketEntity) => "SafetyParsed",
                    nameof(OnVIFPacketEntity) => "OnvifParsed",
                    _ => "UnknownParsed"
                };
                _statsObserver.AddChannelLatency(channelName, dbWriteLatencyMs);

                var stats = GetStats();
                _logger.LogInformation(
                    "[DB-WRITER] {Entity} Worker {Worker} Batch #{Batch}: Size={BatchSize} Latency={Latency:F1}ms Channel={Channel} | Total Flushed={TotalFlushed} Failed={TotalFailed} AvgLatency={AvgLatency:F1}ms",
                    typeof(T).Name, workerId, batchNumber, batchSize, dbWriteLatencyMs, channelCount, stats.Flushed, stats.Failed, stats.AvgLatencyMs);
            }
            catch
            {
                _statsObserver.DbWriter.AddFailed(batch.Count);
                throw;
            }
        }
        catch (Exception ex)
        {
            _statsObserver.DbWriter.AddFailed(batch.Count);
            _logger.LogError(ex, "Batch #{Batch} insert failed for {Entity}", batchNumber, typeof(T).Name);
        }
    }
    
    private void UpdateParsedChannelStats()
    {
        // Get channel count from StatsObserver
        var channelCount = _statsObserver.DbWriter.GetChannelCount();
        
        // Get capacity from configuration
        var capacity = GetChannelCapacity();
        var utilization = capacity > 0 ? (double)channelCount / capacity * 100 : 0;
        
        // Determine channel name based on packet type
        var channelName = typeof(T).Name switch
        {
            nameof(MotionPacketEntity) => "MotionParsed",
            nameof(SafetyPacketEntity) => "SafetyParsed",
            nameof(OnVIFPacketEntity) => "OnvifParsed",
            _ => "UnknownParsed"
        };
        
        _statsObserver.UpdateChannelStats(channelName, capacity, channelCount, utilization, _currentWorkers);
    }
    
    private int GetChannelCapacity()
    {
        // Get capacity from configuration based on packet type
        return typeof(T).Name switch
        {
            nameof(MotionPacketEntity) => 1_000_000,   // From configuration
            nameof(SafetyPacketEntity) => 1_000_000,  // From configuration
            nameof(OnVIFPacketEntity) => 100_000,     // From configuration
            _ => 100_000
        };
    }
}
