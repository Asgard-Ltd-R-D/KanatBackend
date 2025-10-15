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

namespace PacketProcessing.Services.Storage;

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

    private long _flushedCount;
    private long _failedCount;

    public DbWriterService(
        ILogger<DbWriterService<T>> logger,
        Channel<T> channel,
        IInfluxRepository<T> repository,
        IOptions<QuestDbConfiguration> options,
        IConfiguration configuration)
    {
        _logger = logger;
        _channel = channel;
        _repository = repository;

        var concurrency = configuration.GetSection("Concurrency");
        _batchSize = concurrency.GetValue<int>("BatchSize", 1000);
        _batchTimeout = TimeSpan.FromMilliseconds(concurrency.GetValue<int>("BatchTimeoutMs", 30));

        var min = concurrency.GetValue<int>("MinWorkers", 2);
        var max = concurrency.GetValue<int>("MaxWorkers", 8);
        _workerCount = Math.Clamp(Environment.ProcessorCount, min, max);

        var opt = options.Value;
        // removed auto_flush_* to avoid double-batching
        _connectionString =
            $"http::addr={opt.Host}:{opt.InfluxPort};username={opt.Username};password={opt.Password};";
        
        _logger.LogInformation(
            "[DB-WRITER] {Entity} initialized with {Workers} workers, BatchSize={BatchSize}, Timeout={Timeout}ms",
            typeof(T).Name, _workerCount, _batchSize, _batchTimeout.TotalMilliseconds);
    }

    // ----------- BackgroundService entry point -----------
    protected override Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("[DB-WRITER] {Entity} Starting {Workers} worker loops...", typeof(T).Name, _workerCount);
        
        var workers = Enumerable.Range(0, _workerCount)
            .Select(i => Task.Factory.StartNew(
                    () => WorkerLoopAsync(i, stoppingToken),
                    stoppingToken,
                    TaskCreationOptions.LongRunning,
                    TaskScheduler.Default)
                .Unwrap())
            .ToArray();

        _logger.LogInformation("[DB-WRITER] {Entity} All {Workers} workers started", typeof(T).Name, _workerCount);
        return Task.WhenAll(workers);
    }

    private async Task WorkerLoopAsync(int workerId, CancellationToken token)
    {
        using var scope = _logger.BeginScope(new Dictionary<string, object>
        {
            ["Worker"] = workerId,
            ["Entity"] = typeof(T).Name
        });
    
        ISender? sender = null;
        var buffer = new List<T>(_batchSize);
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
                        // Drain fast if more are available
                        while (buffer.Count < _batchSize && _channel.Reader.TryRead(out var more))
                        {
                            buffer.Add(more);
                            if (!oldestInBufferUtc.HasValue || more.Timestamp < oldestInBufferUtc.Value)
                                oldestInBufferUtc = more.Timestamp;
                        }

                        // Flush if full or latency cap reached
                        if (buffer.Count >= _batchSize ||
                            (oldestInBufferUtc.HasValue &&
                                (DateTime.UtcNow - oldestInBufferUtc.Value) >= _batchTimeout))
                        {
                            await FlushInternalAsync(sender, buffer, workerId, oldestInBufferUtc, token);
                            buffer.Clear();
                            oldestInBufferUtc = null;
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
                    if (buffer.Count > 0)
                    {
                        await FlushInternalAsync(sender, buffer, workerId, oldestInBufferUtc, token);
                        buffer.Clear();
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
            if (buffer.Count > 0 && sender is not null)
                await FlushInternalAsync(sender, buffer, workerId, oldestInBufferUtc, token);
                buffer.Clear();
        }
        catch (OperationCanceledException)
        {
            // Shutdown requested — final flush
            if (buffer.Count > 0 && sender is not null)
                await FlushInternalAsync(sender, buffer, workerId, oldestInBufferUtc, token);
                buffer.Clear();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[{Entity}] Worker {Worker} crashed", typeof(T).Name, workerId);
            throw;
        }
        finally
        {
            sender?.Dispose();
        }
    }

    public (long Flushed, long Failed) GetStats() =>
        (Interlocked.Read(ref _flushedCount), Interlocked.Read(ref _failedCount));

    // ----------- Internal logic -----------
    private async Task FlushInternalAsync(ISender sender, IReadOnlyList<T> batch, int workerId, DateTime? oldestInBufferUtc, CancellationToken ct)
    {
        if (batch.Count == 0) return;
        
        var batchSize = batch.Count;
        var oldest = oldestInBufferUtc ?? DateTime.UtcNow;
        var latencyMs = (DateTime.UtcNow - oldest).TotalMilliseconds;

        try
        {
            await _repository.WriteBatchQuestDbAsync(sender, batch, ct);
            Interlocked.Add(ref _flushedCount, batch.Count);
            
            var (totalFlushed, totalFailed) = GetStats();
            _logger.LogInformation(
                "[DB-WRITER] {Entity} Worker {Worker}: Batch=(Size:{BatchSize} Latency:{Latency:F1}ms) Total=(Flushed:{TotalFlushed} Failed:{TotalFailed})",
                typeof(T).Name, workerId, batchSize, latencyMs, totalFlushed, totalFailed);
        }
        catch (Exception ex) when (ex is IOException || ex is SocketException || ex.GetType().Name.Contains("Ingress"))
        {
            _logger.LogWarning(ex, "ILP write failed, recreating sender and retrying...");
            sender.Dispose();
            sender = Sender.New(_connectionString);
            try
            {
                await _repository.WriteBatchQuestDbAsync(sender, batch, ct);
                Interlocked.Add(ref _flushedCount, batch.Count);

                var (totalFlushed, totalFailed) = GetStats();
                _logger.LogInformation(
                    "[DB-WRITER] {Entity} Worker {Worker}: Batch=(Size:{BatchSize} Latency:{Latency:F1}ms) Total=(Flushed:{TotalFlushed} Failed:{TotalFailed})",
                    typeof(T).Name, workerId, batchSize, latencyMs, totalFlushed, totalFailed);
            }
            catch
            {
                Interlocked.Add(ref _failedCount, batch.Count);
                throw;
            }
        }
        catch (Exception ex)
        {
            Interlocked.Add(ref _failedCount, batch.Count);
            _logger.LogError(ex, "Batch insert failed for {Entity}", typeof(T).Name);
        }
    }
}
