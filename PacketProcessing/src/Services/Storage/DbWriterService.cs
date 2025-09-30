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
        _batchSize = concurrency.GetValue<int>("BatchSize", 500);
        _batchTimeout = TimeSpan.FromMilliseconds(concurrency.GetValue<int>("BatchTimeoutMs", 100));

        var min = concurrency.GetValue<int>("MinWorkers", 2);
        var max = concurrency.GetValue<int>("MaxWorkers", 8);
        _workerCount = Math.Clamp(Environment.ProcessorCount, min, max);

        var opt = options.Value;
        // removed auto_flush_* to avoid double-batching
        _connectionString =
            $"http::addr={opt.Host}:{opt.InfluxPort};username={opt.Username};password={opt.Password};" +
            $"auto_flush_rows={opt.BatchSize};auto_flush_interval={opt.BatchTimeoutMs};";
    }

    // ----------- BackgroundService entry point -----------
    protected override Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var workers = Enumerable.Range(0, _workerCount)
            .Select(i => Task.Run(() => WorkerLoopAsync(i, stoppingToken), stoppingToken))
            .ToArray();

        return Task.WhenAll(workers);
    }

    private async Task WorkerLoopAsync(int workerId, CancellationToken token)
    {
        ISender? sender = null;
        var buffer = new List<T>(_batchSize);
        var lastFlush = DateTime.UtcNow;
        var logTicker = new PeriodicTimer(TimeSpan.FromSeconds(10));

        try
        {
            sender = Sender.New(_connectionString);

            await foreach (var packet in _channel.Reader.ReadAllAsync(token))
            {
                buffer.Add(packet);

                // Drain aggressively up to batch size
                while (buffer.Count < _batchSize && _channel.Reader.TryRead(out var more))
                    buffer.Add(more);

                var timeExceeded = (DateTime.UtcNow - lastFlush) >= _batchTimeout;
                var sizeExceeded = buffer.Count >= _batchSize;

                if (sizeExceeded || timeExceeded)
                {
                    await FlushInternalAsync(sender, buffer, token);
                    buffer.Clear();
                    lastFlush = DateTime.UtcNow;
                }

                if (await logTicker.WaitForNextTickAsync(token))
                {
                    var (flushed, failed) = GetStats();
                    _logger.LogInformation(
                        "[{Entity}] Worker {Worker} Stats: Flushed={Flushed}, Failed={Failed}",
                        typeof(T).Name, workerId, flushed, failed);
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
