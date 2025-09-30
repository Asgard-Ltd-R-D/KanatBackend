using System.Net.Sockets;
using System.Threading.Channels;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using PacketProcessing.Entities;
using PacketProcessing.Repositories.InfluxRepository;
using PacketProcessing.Utils.Records;
using QuestDB.Senders;
using QuestDB;
using Microsoft.Extensions.Configuration;

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

    private long _flushedCount;
    private long _failedCount;

    public DbWriterService(
        ILogger<DbWriterService<T>> logger,
        Channel<T> channel,
        IInfluxRepository<T> repository,
        IOptions<InfluxDbOptions> options,
        IConfiguration configuration)
    {
        _logger = logger;
        _channel = channel;
        _repository = repository;

        var concurrency = configuration.GetSection("Concurrency");
        _batchSize = concurrency.GetValue<int>("BatchSize", 500);
        _batchTimeout = TimeSpan.FromMilliseconds(concurrency.GetValue<int>("BatchTimeoutMs", 100));

        var opt = options.Value;
        _connectionString =
            $"http::addr={opt.Host}:{opt.Port};username={opt.Username};password={opt.Password};" +
            $"auto_flush_rows={opt.BatchSize};auto_flush_interval={opt.BatchTimeoutMs};";
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        ISender? sender = null;
        var buffer = new List<T>(_batchSize);
        var lastFlush = DateTime.UtcNow;
        var logTicker = new PeriodicTimer(TimeSpan.FromSeconds(10));

        try
        {
            sender = Sender.New(_connectionString);

            await foreach (var packet in _channel.Reader.ReadAllAsync(stoppingToken))
            {
                buffer.Add(packet);

                var timeExceeded = (DateTime.UtcNow - lastFlush) >= _batchTimeout;
                var sizeExceeded = buffer.Count >= _batchSize;

                if (sizeExceeded || timeExceeded)
                {
                    await FlushInternalAsync(sender, buffer, stoppingToken);
                    buffer.Clear();
                    lastFlush = DateTime.UtcNow;
                }

                if (await logTicker.WaitForNextTickAsync(stoppingToken))
                {
                    var (flushed, failed) = GetStats();
                    _logger.LogInformation("[{Entity}] DbWriter Stats: Flushed={Flushed}, Failed={Failed}",
                        typeof(T).Name, flushed, failed);
                }
            }
        }
        catch (OperationCanceledException) { /* shutdown */ }
        catch (Exception ex)
        {
            _logger.LogError(ex, "DbWriter crashed for {Entity}", typeof(T).Name);
        }
        finally
        {
            try { sender?.Dispose(); } catch { }
        }

        if (buffer.Count > 0 && sender is not null)
            await FlushInternalAsync(sender, buffer, stoppingToken);
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
