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
        var max = concurrency.GetValue<int>("MaxWorkers", 5);
        _workerCount = Math.Clamp(Environment.ProcessorCount, min, max);

        var opt = options.Value;
        // removed auto_flush_* to avoid double-batching
        _connectionString =
            $"http::addr={opt.Host}:{opt.InfluxPort};username={opt.Username};password={opt.Password};";
    }

    // ----------- BackgroundService entry point -----------
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
        ISender? sender = null;
        var buffer = new List<T>(_batchSize);
        var sw = System.Diagnostics.Stopwatch.StartNew();
        long lastFlushMs = sw.ElapsedMilliseconds;
        long lastLogMs = sw.ElapsedMilliseconds;
        const int LOG_PERIOD_MS = 10_000;

        try
        {
            sender = Sender.New(_connectionString);

            await foreach (var packet in _channel.Reader.ReadAllAsync(token))
            {
                // Block for first item to start a batch
                var first = await _channel.Reader.ReadAsync(token);
                buffer.Clear();
                buffer.Add(first);

                // Drain what's immediately available
                while (buffer.Count < _batchSize && _channel.Reader.TryRead(out var more))
                    buffer.Add(more);

                // Set a deadline for soft-wait fill
                long deadlineMs = sw.ElapsedMilliseconds + (long)_batchTimeout.TotalMilliseconds;

                // Soft-wait until deadline to pick up a few more items
                while (buffer.Count < _batchSize)
                {
                    var now = sw.ElapsedMilliseconds;
                    var remainingMs = (int)(deadlineMs - now);
                    if (remainingMs <= 0) break;

                    // Timed wait for one more; if it arrives, drain fast-path items
                    var readTask = _channel.Reader.ReadAsync(token).AsTask();
                    var delayTask = Task.Delay(remainingMs, token);
                    var completed = await Task.WhenAny(readTask, delayTask);
                    if (completed == readTask)
                    {
                        buffer.Add(readTask.Result);
                        while (buffer.Count < _batchSize && _channel.Reader.TryRead(out var add))
                            buffer.Add(add);
                    }
                    else
                    {
                        break; // deadline hit
                    }
                }

                // Flush the batch (full or deadline)
                await FlushInternalAsync(sender, buffer, token);
                lastFlushMs = sw.ElapsedMilliseconds;

                // Non-blocking periodic log
                if (sw.ElapsedMilliseconds - lastLogMs >= LOG_PERIOD_MS)
                {
                    var (flushed, failed) = GetStats();
                    _logger.LogInformation("[{Entity}] Worker {Worker} Flushed={Flushed} Failed={Failed} BatchSize={Batch} TimeoutMs={Timeout}",
                        typeof(T).Name, workerId, flushed, failed, _batchSize, (int)_batchTimeout.TotalMilliseconds);
                    lastLogMs = sw.ElapsedMilliseconds;
                }
            }
        }
        catch (OperationCanceledException) { /* shutdown */ }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[{Entity}] Worker {Worker} crashed", typeof(T).Name, workerId);
            throw;
        }
        finally
        {
            if (buffer.Count > 0 && sender is not null)
                await FlushInternalAsync(sender, buffer, token);
            sender?.Dispose();
        }
    }

    // ----------- IDbWriterService<T> Implementation -----------
    public async Task FlushBatchAsync(CancellationToken ct = default)
    {
        using var sender = Sender.New(_connectionString);
        var drained = new List<T>();
        while (_channel.Reader.TryRead(out var item))
            drained.Add(item);

        if (drained.Count > 0)
            await FlushInternalAsync(sender, drained, ct);
    }

    public (long Flushed, long Failed) GetStats() =>
        (Interlocked.Read(ref _flushedCount), Interlocked.Read(ref _failedCount));

    // ----------- Internal logic -----------
    private async Task FlushInternalAsync(ISender sender, IReadOnlyList<T> batch, CancellationToken ct)
    {
        if (batch.Count == 0) return;

        try
        {
            await _repository.WriteBatchQuestDbAsync(sender, batch, ct);
            Interlocked.Add(ref _flushedCount, batch.Count);
            _logger.LogInformation("Flushed {Count} packets of {Entity} into DB",
                batch.Count, typeof(T).Name);
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
