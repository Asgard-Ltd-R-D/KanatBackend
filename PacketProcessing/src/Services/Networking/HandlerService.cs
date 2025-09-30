using System.Net.Sockets;
using System.Threading.Channels;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Options;
using PacketProcessing.Entities;
using PacketProcessing.Services.Networking;
using PacketProcessing.Utils.Parsers;
using PacketProcessing.Repositories.InfluxRepository;
using QuestDB.Senders;
using QuestDB;
using PacketProcessing.Utils.Filters;
using PacketProcessing.Config;

namespace PacketProcessing.Services.Networking;

public class HandlerService<T> : BackgroundService, IHandlerService<T>
    where T : BasePacketEntity
{
    private readonly ILogger<HandlerService<T>> _logger;

    private readonly IInfluxRepository<T> _repository; // The repository to flush the batches

    // The filter configuration
    private readonly string _protocol;
    private readonly IEnumerable<string> _ips;

    // The concurrency configuration
    private readonly Channel<T> _channel;
    private readonly int _batchSize;
    private readonly TimeSpan _batchTimeout;
    private readonly int _workerCount;
    private readonly string _connectionString;
    private IDisposable? _subscription;

    // The statistics counters
    private long _packetsCaptured;
    private long _packetsParsed;
    private long _packetsDropped;

    public HandlerService(
        string dataPipeName,
        ILogger<HandlerService<T>> logger,
        Channel<T> channel,
        IInfluxRepository<T> repository,
        IOptions<QuestDbConfiguration> options,
        IConfiguration configuration)
    {
        _logger = logger;
        _channel = channel;
        _repository = repository;

        _protocol = configuration.GetValue<string>($"{dataPipeName}:Network:Protocol") ?? "";
        _ips = configuration.GetSection($"{dataPipeName}:Network:IPs").Get<IEnumerable<string>>() ?? [];

        var concurrency = configuration.GetSection("Concurrency");
        _batchSize = concurrency.GetValue<int>("BatchSize", 500);
        _batchTimeout = TimeSpan.FromMilliseconds(concurrency.GetValue<int>("BatchTimeoutMs", 100));

        var min = concurrency.GetValue<int>("MinWorkers", 2);
        var max = concurrency.GetValue<int>("MaxWorkers", 8);
        _logger.LogInformation("Using concurrency configuration: MinWorkers={MinWorkers}, MaxWorkers={MaxWorkers} and batch size={BatchSize} and batch timeout={BatchTimeout}ms", min, max, _batchSize, _batchTimeout.TotalMilliseconds);
        _workerCount = Math.Clamp(Environment.ProcessorCount, min, max);

        var opt = options.Value;
        _connectionString =
            $"http::addr={opt.Host}:{opt.InfluxPort};username={opt.Username};password={opt.Password};" +
            $"auto_flush_rows={opt.BatchSize};auto_flush_interval={opt.BatchTimeoutMs};";

        _logger.LogInformation(
            "{Handler} initialized with {Workers} workers, BatchSize={BatchSize}, Timeout={Timeout}ms",
            typeof(T).Name, _workerCount, _batchSize, _batchTimeout.TotalMilliseconds);
    }

    #region IHandlerService

    public async Task SubscribeToDeviceAsync(IDeviceService deviceService, string deviceName)
    {
        var filter = BpfFilterBuilder.Build(_protocol, _ips);
        await deviceService.SubscribeWithFilterAsync(this, deviceName, filter);
        _subscription = deviceService.Subscribe(this);
        _logger.LogInformation("{Handler} subscribed to {Device} with filter {Filter}", typeof(T).Name, deviceName, filter);
    }

    public async Task UnsubscribeAsync(IDeviceService deviceService)
    {
        _subscription?.Dispose();
        _subscription = null;

        await deviceService.UnsubscribeAsync(this);

        Interlocked.Exchange(ref _packetsCaptured, 0);
        Interlocked.Exchange(ref _packetsParsed, 0);
        Interlocked.Exchange(ref _packetsDropped, 0);

        _logger.LogInformation("{Handler} unsubscribed", typeof(T).Name);
    }

    public (long Captured, long Parsed, long Dropped) GetStats() =>
        (Interlocked.Read(ref _packetsCaptured),
         Interlocked.Read(ref _packetsParsed),
         Interlocked.Read(ref _packetsDropped));

    #endregion

    #region IObserver<RawPacketEvent>

    public void OnNext(RawPacketEvent evt)
    {
        Interlocked.Increment(ref _packetsCaptured);

        try
        {
            var parsed = Parse(evt.Data.Span);
            if (parsed is null)
            {
                Interlocked.Increment(ref _packetsDropped);
                return;
            }

            if (!_channel.Writer.TryWrite(parsed))
                Interlocked.Increment(ref _packetsDropped);
            else
                Interlocked.Increment(ref _packetsParsed);
        }
        catch (Exception ex)
        {
            Interlocked.Increment(ref _packetsDropped);
            _logger.LogError(ex, "Error handling packet from {Device}", evt.DeviceName);
        }
    }

    public void OnError(Exception error) =>
        _logger.LogError(error, "Device service signaled error");

    public void OnCompleted()
    {
        _logger.LogInformation("Device service completed");
        _channel.Writer.Complete();
    }

    #endregion

    #region BackgroundService

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

                var timeExceeded = (DateTime.UtcNow - lastFlush) >= _batchTimeout;
                var sizeExceeded = buffer.Count >= _batchSize;

                if (sizeExceeded || timeExceeded)
                {
                    await FlushBatchAsync(sender, buffer, token);
                    buffer.Clear();
                    lastFlush = DateTime.UtcNow;
                }

                if (await logTicker.WaitForNextTickAsync(token))
                {
                    var (captured, parsed, dropped) = GetStats();
                    _logger.LogInformation("[{Entity}] Worker {Worker} Stats: Captured={Captured}, Parsed={Parsed}, Dropped={Dropped}, Success={Success:P1}",
                        typeof(T).Name, workerId, captured, parsed, dropped,
                        captured > 0 ? (double)parsed / captured : 0.0);
                }
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Worker {Worker} crashed, restarting...", workerId);
            if (!token.IsCancellationRequested)
                _ = Task.Run(() => WorkerLoopAsync(workerId, token), token);
        }
        finally
        {
            try { sender?.Dispose(); } catch { }
        }

        if (buffer.Count > 0 && sender is not null)
            await FlushBatchAsync(sender, buffer, token);
    }

    private async Task FlushBatchAsync(ISender sender, IReadOnlyList<T> batch, CancellationToken ct)
    {
        if (batch.Count == 0) return;

        try
        {
            await _repository.WriteBatchQuestDbAsync(sender, batch, ct);
            _logger.LogInformation("Flushed {Count} packets of {Entity}", batch.Count, typeof(T).Name);
        }
        catch (Exception ex) when (ex is IOException || ex is SocketException || ex.GetType().Name.Contains("Ingress"))
        {
            _logger.LogWarning(ex, "ILP write failed, recreating sender and retrying...");
            sender.Dispose();
            sender = Sender.New(_connectionString); // recreate sender
            await _repository.WriteBatchQuestDbAsync(sender, batch, ct);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Batch insert failed for {Entity}", typeof(T).Name);
        }
    }

    #endregion

    private static T? Parse(ReadOnlySpan<byte> raw)
    {
        if (raw.IsEmpty) return null;
        try { return ParseMapper.Map<T>(raw); }
        catch { return null; }
    }
}
