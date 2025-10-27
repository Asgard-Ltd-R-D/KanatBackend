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
using PacketProcessing.Telemetry;
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
    private readonly int _workerCount;
    private readonly StatsObserver _statsObserver;

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
        
        _logger.LogInformation(
            "[DB-WRITER] {Entity} initialized with {Workers} workers, BatchSize={BatchSize}, Timeout={Timeout}ms",
            typeof(T).Name, _workerCount, _batchSize, _batchTimeout.TotalMilliseconds);
    }

    // ----------- BackgroundService entry point -----------
    protected override Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("[DB-WRITER] {Entity} Starting {Workers} worker loops...", typeof(T).Name, _workerCount);
        
        // Avoid LINQ allocations - use direct array allocation
        var workers = new Task[_workerCount];
        for (int i = 0; i < _workerCount; i++)
        {
            int workerId = i; // Capture variable for closure
            workers[i] = Task.Factory.StartNew(
                () => WorkerLoopAsync(workerId, stoppingToken),
                stoppingToken,
                TaskCreationOptions.LongRunning,
                TaskScheduler.Default)
            .Unwrap();
        }

        _logger.LogInformation("[DB-WRITER] {Entity} All {Workers} workers started", typeof(T).Name, _workerCount);
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
                    if (dataAvailableTask.Result) {
                        // Aggressive draining: Read first item, then drain as many as possible
                        // This minimizes context switches and maximizes throughput
                        if (_channel.Reader.TryRead(out var firstItem))
                        {
                            rentedArray[bufferCount] = firstItem;
                            bufferCount++;
                            
                            if (!oldestInBufferUtc.HasValue || firstItem.Timestamp < oldestInBufferUtc.Value)
                                oldestInBufferUtc = firstItem.Timestamp;
                            
                            // Now drain remaining items without blocking
                            // Loop unrolled for better performance - check 8 items at once
                            while (bufferCount < _batchSize)
                            {
                                // Try to read in chunks for better cache performance
                                int itemsToRead = Math.Min(8, _batchSize - bufferCount);
                                int itemsRead = 0;
                                
                                for (int i = 0; i < itemsToRead; i++)
                                {
                                    if (_channel.Reader.TryRead(out var more))
                                    {
                                        rentedArray[bufferCount] = more;
                                        bufferCount++;
                                        itemsRead++;
                                        
                                        if (!oldestInBufferUtc.HasValue || more.Timestamp < oldestInBufferUtc.Value)
                                            oldestInBufferUtc = more.Timestamp;
                                    }
                                    else
                                    {
                                        break;
                                    }
                                }
                                
                                // If we couldn't read any items, channel is temporarily empty
                                if (itemsRead == 0)
                                    break;
                            }
                        }
                        
                        // Decrement channel count as items are read from channel into buffer
                        _statsObserver.DbWriter.AddChannelCount(-bufferCount);
                        
                        // Update channel stats after reading (items are now in buffer, not in channel)
                        UpdateParsedChannelStats();

                        // Flush if full or latency cap reached
                        if (bufferCount >= _batchSize ||
                            (bufferCount > 0 && oldestInBufferUtc.HasValue &&
                                (DateTime.UtcNow - oldestInBufferUtc.Value) >= _batchTimeout))
                        {
                            // Create ArraySegment view - zero-copy wrapper around filled portion
                            var segment = new ArraySegment<T>(rentedArray, 0, bufferCount);
                            await FlushInternalAsync(sender, segment, workerId, oldestInBufferUtc, token);
                            bufferCount = 0;
                            oldestInBufferUtc = null;
                            
                            // Update parsed channel stats after flushing
                            UpdateParsedChannelStats();
                        }
                    }
                    else
                    {
                        // Channel completed; break and final-drain below
                        break;
                    }
                }

                else // tick fired
                {
                    var ticked = await tickTask; // will be true unless timer disposed
                    if (!ticked) break; // safety; normally only false when timer disposed

                    // Timer tick: if there is anything pending -> flush.
                    if (bufferCount > 0)
                    {
                        var segment = new ArraySegment<T>(rentedArray, 0, bufferCount);
                        await FlushInternalAsync(sender, segment, workerId, oldestInBufferUtc, token);
                        bufferCount = 0;
                        oldestInBufferUtc = null;
                    }
                    
                    // Start the next tick wait now that the previous completed
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
                await FlushInternalAsync(sender, segment, workerId, oldestInBufferUtc, token);
                bufferCount = 0;
            }
        }
        catch (OperationCanceledException)
        {
            // Shutdown requested — final flush
            if (bufferCount > 0 && sender is not null)
            {
                var segment = new ArraySegment<T>(rentedArray, 0, bufferCount);
                await FlushInternalAsync(sender, segment, workerId, oldestInBufferUtc, token);
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
    private async Task FlushInternalAsync(ISender sender, IReadOnlyList<T> batch, int workerId, DateTime? oldestInBufferUtc, CancellationToken ct)
    {
        if (batch.Count == 0) return;
        
        var batchSize = batch.Count;
        var oldest = oldestInBufferUtc ?? DateTime.UtcNow;
        var writeStartTime = DateTime.UtcNow;
        var dbWriteLatencyMs = 0.0;

        try
        {
            await _repository.WriteBatchQuestDbAsync(sender, batch, ct);
            var writeEndTime = DateTime.UtcNow;
            dbWriteLatencyMs = (writeEndTime - oldest).TotalMilliseconds; // Time from oldest packet to write completion
            
            _statsObserver.DbWriter.AddFlushed(batch.Count);
            _statsObserver.DbWriter.AddParsed(batch.Count); // Increment parsed count when actually written to DB
            
            // Track DB write latency (actual database write time)
            _statsObserver.DbWriter.AddLatency((long)dbWriteLatencyMs);
            
            var stats = GetStats();
            _logger.LogInformation(
                "[DB-WRITER] {Entity} Worker {Worker}: Batch=(Size:{BatchSize} Latency:{Latency:F1}ms) Total=(Flushed:{TotalFlushed} Failed:{TotalFailed} AvgLatency:{AvgLatency:F1}ms)",
                typeof(T).Name, workerId, batchSize, dbWriteLatencyMs, stats.Flushed, stats.Failed, stats.AvgLatencyMs);
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

                var stats = GetStats();
                _logger.LogInformation(
                    "[DB-WRITER] {Entity} Worker {Worker}: Batch=(Size:{BatchSize} Latency:{Latency:F1}ms) Total=(Flushed:{TotalFlushed} Failed:{TotalFailed} AvgLatency:{AvgLatency:F1}ms)",
                    typeof(T).Name, workerId, batchSize, dbWriteLatencyMs, stats.Flushed, stats.Failed, stats.AvgLatencyMs);
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
            _logger.LogError(ex, "Batch insert failed for {Entity}", typeof(T).Name);
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
        
        _statsObserver.UpdateChannelStats(channelName, capacity, channelCount, utilization);
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
