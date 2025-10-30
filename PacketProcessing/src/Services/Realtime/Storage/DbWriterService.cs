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
    private readonly string _entityName;
    private readonly IConfiguration _configuration;

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
        _configuration = configuration;

        var concurrency = configuration.GetSection("Concurrency");
        _batchSize = concurrency.GetValue<int>("BatchSize", 1000);
        _batchTimeout = TimeSpan.FromMilliseconds(concurrency.GetValue<int>("BatchTimeoutMs", 30));
        _entityName = typeof(T) == typeof(Entities.Packet.MotionPacketEntity) ? "Motion" :
                      typeof(T) == typeof(Entities.Packet.SafetyPacketEntity) ? "Safety" :
                      typeof(T) == typeof(Entities.Packet.OnVIFPacketEntity) ? "OnVIF" : "Unknown";
        var min = concurrency.GetValue<int>("MinWorkers", 2);
        var max = concurrency.GetValue<int>("MaxWorkers", 8);
        _workerCount = Math.Clamp(Environment.ProcessorCount, min, max);

        var opt = options.Value;
        // Optimize connection string for high-throughput ingestion
        _connectionString =
            $"http::addr={opt.Host}:{opt.InfluxPort};" +
            $"username={opt.Username};password={opt.Password};" +
            $"request_min_throughput=500000;" +  // Target 500K packets/sec throughput
            $"request_timeout=5000;" +            // 5 second timeout for requests
            $"retry_timeout=1000;";
        
        var parsedCapacity = GetChannelCapacity();
        _logger.LogInformation(
            "[DB-WRITER] {Entity} initialized with {Workers} workers (ParsedChannelCapacity:{ParsedCap}, BatchSize:{BatchSize}, Timeout:{Timeout}ms)",
            typeof(T).Name, _workerCount, parsedCapacity, _batchSize, _batchTimeout.TotalMilliseconds);
    }

    // ----------- BackgroundService entry point -----------
    protected override Task ExecuteAsync(CancellationToken stoppingToken)
    {        
        // Avoid LINQ allocations - use direct array allocation
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
        var dbWriteLatencyMs = 0.0;           // Pure DB write duration
        var queueLatencyMs = 0.0;             // Time spent buffered before write starts

        try
        {
            // Measure queue time up to the start of DB write
            queueLatencyMs = (writeStartTime - oldest).TotalMilliseconds;
            await _repository.WriteBatchQuestDbAsync(sender, batch, ct);
            var writeEndTime = DateTime.UtcNow;
            dbWriteLatencyMs = (writeEndTime - writeStartTime).TotalMilliseconds; // Pure DB write time
            
            _statsObserver.DbWriter.AddFlushed(batch.Count);
            var entityName = typeof(T) == typeof(Entities.Packet.MotionPacketEntity) ? "Motion" :
                             typeof(T) == typeof(Entities.Packet.SafetyPacketEntity) ? "Safety" :
                             typeof(T) == typeof(Entities.Packet.OnVIFPacketEntity) ? "OnVIF" : "Unknown";
            _statsObserver.IncrementFlushFor(entityName, success: true);
            _statsObserver.DbWriter.AddParsed(batch.Count); // Increment parsed count when actually written to DB
            
            // Track queue latency for parsed channel telemetry (more indicative of backpressure)
            _statsObserver.DbWriter.AddLatency((long)queueLatencyMs);
            
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
                "[DB-WRITER] {Entity} Worker {Worker}: Batch=(Size:{BatchSize} Queue:{QueueMs:F1}ms Write:{WriteMs:F1}ms) Total=(Flushed:{TotalFlushed} Failed:{TotalFailed} AvgQueue:{AvgLatency:F1}ms)",
                typeof(T).Name, workerId, batchSize, queueLatencyMs, dbWriteLatencyMs, stats.Flushed, stats.Failed, stats.AvgLatencyMs);
        }
        catch (Exception ex) when (ex is IOException || ex is SocketException || ex.GetType().Name.Contains("Ingress"))
        {
            _logger.LogWarning(ex, "ILP write failed, recreating sender and retrying...");
            sender.Dispose();
            sender = Sender.New(_connectionString);
            try
            {
                // Recompute queue time relative to the original oldest timestamp
                queueLatencyMs = (writeStartTime - oldest).TotalMilliseconds;
                await _repository.WriteBatchQuestDbAsync(sender, batch, ct);
                var writeEndTime = DateTime.UtcNow;
                dbWriteLatencyMs = (writeEndTime - writeStartTime).TotalMilliseconds; // Pure DB write time
                
                _statsObserver.DbWriter.AddFlushed(batch.Count);
                _statsObserver.IncrementFlushFor(_entityName, success: true);
                _statsObserver.DbWriter.AddParsed(batch.Count); // Increment parsed count when actually written to DB
                
                // Track queue latency for parsed channel telemetry
                _statsObserver.DbWriter.AddLatency((long)queueLatencyMs);

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
                    "[DB-WRITER] {Entity} Worker {Worker}: Batch=(Size:{BatchSize} Queue:{QueueMs:F1}ms Write:{WriteMs:F1}ms) Total=(Flushed:{TotalFlushed} Failed:{TotalFailed} AvgQueue:{AvgLatency:F1}ms)",
                    typeof(T).Name, workerId, batchSize, queueLatencyMs, dbWriteLatencyMs, stats.Flushed, stats.Failed, stats.AvgLatencyMs);
            }
            catch
            {
                _statsObserver.DbWriter.AddFailed(batch.Count);
                _statsObserver.IncrementFlushFor(_entityName, success: false);
                throw;
            }
        }
        catch (Exception ex)
        {
            _statsObserver.DbWriter.AddFailed(batch.Count);
            _statsObserver.IncrementFlushFor(_entityName, success: false);
            _logger.LogError(ex, "Batch insert failed for {Entity}", typeof(T).Name);
        }
    }
    
    private void UpdateParsedChannelStats()
    {
        // Get channel count from StatsObserver
        var channelCount = _statsObserver.DbWriter.GetChannelCount();
        
        // Get capacity from configuration
        var capacity = GetChannelCapacity();
        var utilization = capacity > 0 ? (double) channelCount / capacity * 100 : 0;
        
        // Determine channel name based on packet type
        var channelName = typeof(T).Name switch
        {
            nameof(MotionPacketEntity) => "MotionParsed",
            nameof(SafetyPacketEntity) => "SafetyParsed",
            nameof(OnVIFPacketEntity) => "OnvifParsed",
            _ => "UnknownParsed"
        };
        
        var avgLatency = _statsObserver.DbWriter.GetAverageLatency();
        _statsObserver.UpdateChannelStats(channelName, capacity, channelCount, utilization, _workerCount, avgLatency);
    }
    
    private int GetChannelCapacity()
    {
        // Get capacity from configuration based on packet type
        // Match ConfigurationInjection.cs keys: DataPipes:{Pipe}:Channel:Members
        // Defaults align with DI fallbacks
        var capacityKey = typeof(T).Name switch
        {
            nameof(MotionPacketEntity) => "DataPipes:MotionCapture:Channel:Members",
            nameof(SafetyPacketEntity) => "DataPipes:SafetyCapture:Channel:Members",
            nameof(OnVIFPacketEntity) => "DataPipes:OnVIFCapture:Channel:Members",
            _ => string.Empty
        };

        if (!string.IsNullOrEmpty(capacityKey))
        {
            // IConfiguration is available via constructor (variable name 'configuration')
            try
            {
                var cfg = (IConfiguration?)typeof(DbWriterService<T>)
                    .GetField("configuration", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)?
                    .GetValue(this);

                // Fallback: use options injected earlier if reflection fails
                if (cfg == null)
                {
                    // 'configuration' was passed in constructor; keep a private field for it
                }
            }
            catch { }
        }

        // Direct read from constructor-captured configuration (added private field)
        return _configuration.GetValue<int>(capacityKey,
            typeof(T).Name switch
            {
                nameof(MotionPacketEntity) => 1_000_000,
                nameof(SafetyPacketEntity) => 1_000_000,
                nameof(OnVIFPacketEntity) => 100_000,
                _ => 100_000
            });
    }
}
