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
    private readonly int _parsedChannelCapacity;

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

        // Determine data pipe key and get parsed channel capacity from appsettings
        // We reuse the same Channel:Members setting defined per DataPipes section
        string dataPipeKey = typeof(T).Name switch
        {
            nameof(MotionPacketEntity) => "DataPipes:MotionCapture",
            nameof(SafetyPacketEntity) => "DataPipes:SafetyCapture",
            nameof(OnVIFPacketEntity) => "DataPipes:OnVIFCapture",
            _ => "DataPipes:MotionCapture"
        };
        _parsedChannelCapacity = configuration.GetValue<int>($"{dataPipeKey}:Channel:Members", 100_000);

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

        var workerCancellationTokens = new Dictionary<int, CancellationTokenSource>();
        var workerTasks = new Dictionary<int, Task>(); // NEW

        // Push initial parsed channel stats so capacity appears in telemetry immediately
        UpdateParsedChannelStats();

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
            workerTasks[workerId] = task; // NEW
        }

        _logger.LogInformation("[DB-WRITER] {Entity} All {Workers} workers started", typeof(T).Name, _workerCount);

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
        var checkInterval = TimeSpan.FromSeconds(10); // sampling cadence
        using var timer = new PeriodicTimer(checkInterval);

        // Decision windows per your spec
        var scaleUpWindow   = TimeSpan.FromSeconds(30);
        var scaleDownWindow = TimeSpan.FromMinutes(1);

        // Cooldowns equal to the windows
        var scaleUpCooldown   = scaleUpWindow;
        var scaleDownCooldown = scaleDownWindow;

        TimeSpan highLatencyElapsed = TimeSpan.Zero;
        TimeSpan lowLatencyElapsed  = TimeSpan.Zero;

        double targetMs = _batchTimeout.TotalMilliseconds; // base latency is _batchTimeout
        DateTime nextDecisionNotBefore = DateTime.UtcNow;

        int nextWorkerId = workerCancellationTokens.Count;

        try
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                await timer.WaitForNextTickAsync(stoppingToken);

                // Enforce cooldown after any scale action
                if (DateTime.UtcNow < nextDecisionNotBefore)
                {
                    _logger.LogDebug("[AUTO-SCALER][DB] Cooling down until {Until:o}", nextDecisionNotBefore);
                    continue;
                }

                var currentLatency = _statsObserver.DbWriter.GetAverageLatency();
                var currentWorkers = _currentWorkers;

                // Update elapsed windows
                if (currentLatency > targetMs)
                {
                    highLatencyElapsed += checkInterval;
                    lowLatencyElapsed = TimeSpan.Zero;
                }
                else if (currentLatency > 0) // 0 means "no samples yet"
                {
                    lowLatencyElapsed += checkInterval;
                    highLatencyElapsed = TimeSpan.Zero;
                }
                else
                {
                    highLatencyElapsed = TimeSpan.Zero;
                    lowLatencyElapsed  = TimeSpan.Zero;
                }

                _logger.LogDebug(
                    "[AUTO-SCALER][DB] {Entity} Workers={Workers} Latency={Latency:F1}ms Target={Target:F1}ms | HighElapsed={High}s LowElapsed={Low}s",
                    typeof(T).Name, currentWorkers, currentLatency, targetMs,
                    (int)highLatencyElapsed.TotalSeconds, (int)lowLatencyElapsed.TotalSeconds);

                // ---- SCALE UP ----
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
                        "[AUTO-SCALER][DB] {Entity} SCALING UP: {Old} -> {New} (latency {Latency:F1}ms > target {Target:F1}ms for {Window}s)",
                        typeof(T).Name, currentWorkers, newWorkers, currentLatency, targetMs, (int)scaleUpWindow.TotalSeconds);

                    var task = Task.Factory.StartNew(
                        () => WorkerLoopAsync(workerId, workerCts.Token),
                        workerCts.Token,
                        TaskCreationOptions.LongRunning,
                        TaskScheduler.Default).Unwrap();

                    workers.Add(task);
                    workerTasks[workerId] = task;

                    // reset window and start cooldown
                    highLatencyElapsed = TimeSpan.Zero;
                    nextDecisionNotBefore = DateTime.UtcNow + scaleUpCooldown;
                    continue;
                }

                // ---- SCALE DOWN ----
                if (currentLatency > 0 &&
                    currentLatency <= targetMs &&
                    currentWorkers > _minWorkers &&
                    lowLatencyElapsed >= scaleDownWindow)
                {
                    int newWorkers = currentWorkers - 1;
                    _currentWorkers = newWorkers;

                    var workerToTerminate = workerCancellationTokens.Keys.Max();

                    _logger.LogInformation(
                        "[AUTO-SCALER][DB] {Entity} SCALING DOWN: {Old} -> {New} (latency {Latency:F1}ms ≤ target {Target:F1}ms for {Window}s)",
                        typeof(T).Name, currentWorkers, newWorkers, currentLatency, targetMs, (int)scaleDownWindow.TotalSeconds);

                    if (workerCancellationTokens.TryGetValue(workerToTerminate, out var cts))
                    {
                        // Signal graceful stop; worker will flush then exit
                        cts.Cancel();

                        // Await the worker task so it actually finishes before we proceed
                        if (workerTasks.TryGetValue(workerToTerminate, out var wt))
                        {
                            try { await wt; }
                            catch (OperationCanceledException) { /* normal */ }
                            catch { /* worker already logs */ }

                            workerTasks.Remove(workerToTerminate);
                            workers.Remove(wt);
                        }

                        cts.Dispose();
                        workerCancellationTokens.Remove(workerToTerminate);

                        _logger.LogInformation(
                            "[AUTO-SCALER][DB] {Entity} Worker {WorkerId} terminated gracefully (remaining {Remaining})",
                            typeof(T).Name, workerToTerminate, newWorkers);
                    }

                    // reset window and start cooldown
                    lowLatencyElapsed = TimeSpan.Zero;
                    nextDecisionNotBefore = DateTime.UtcNow + scaleDownCooldown;
                    continue;
                }
            }
        }
        catch (OperationCanceledException) { /* normal */ }
        finally
        {
            // Caller cleans up remaining CTS
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
            // Update parsed channel stats immediately so AvgLatencyMs reflects latest measurement
            UpdateParsedChannelStats();
            
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
                // Update parsed channel stats immediately so AvgLatencyMs reflects latest measurement
                UpdateParsedChannelStats();

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
        // Capacity read from appsettings per DataPipes section
        return _parsedChannelCapacity;
    }
}
