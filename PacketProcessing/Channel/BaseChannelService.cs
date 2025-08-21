using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using PacketProcessing.Repositories;
using System.Threading.Channels;
using QuestDB;

namespace PacketProcessing.Channel;

public sealed class BaseChannelService<T> : BackgroundService, IChannel<T>
    where T : class
{
    private readonly IRepository<T> _repository;
    private readonly ILogger<BaseChannelService<T>> _logger;

    private readonly Channel<T> _channel;
    private readonly List<Task> _workers = [];
    private readonly List<CancellationTokenSource> _workerCts = [];

    private readonly int _batchSize;
    private readonly int _batchTimeoutMs;
    private readonly int _minWorkers;
    private readonly int _maxWorkers;
    private readonly int _channelCapacity;

    private int _currentQueueSize;
    private int _currentWorkers;

    public BaseChannelService(
        IRepository<T> repository,
        int batchSize,
        int batchTimeoutMs,
        int minWorkers,
        int maxWorkers,
        int channelCapacity,
        ILogger<BaseChannelService<T>> logger)
    {
        _repository       = repository;
        _logger           = logger;
        _batchSize        = Math.Max(1, batchSize);
        _batchTimeoutMs   = Math.Max(1, batchTimeoutMs);
        _minWorkers       = Math.Max(1, minWorkers);
        _maxWorkers       = Math.Max(_minWorkers, maxWorkers);
        _channelCapacity  = Math.Max(_batchSize, channelCapacity);

        var chOpts = new BoundedChannelOptions(_channelCapacity)
        {
            FullMode     = BoundedChannelFullMode.Wait,
            SingleWriter = false,
            SingleReader = false
        };
        
        _channel = System.Threading.Channels.Channel.CreateBounded<T>(chOpts);
    }

    public int CurrentWorkers   => Volatile.Read(ref _currentWorkers);
    public int MaxQueueSize     => _channelCapacity;
    public int CurrentQueueSize => Volatile.Read(ref _currentQueueSize);

    public async ValueTask EnqueueAsync(T packet, CancellationToken ct = default)
    {
        await _channel.Writer.WriteAsync(packet, ct).ConfigureAwait(false);
        Interlocked.Increment(ref _currentQueueSize);
    }

    public bool TryEnqueue(T packet)
    {
        var ok = _channel.Writer.TryWrite(packet);
        if (ok) Interlocked.Increment(ref _currentQueueSize);
        return ok;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        // Start minimum workers
        for (var i = 0; i < _minWorkers; i++) StartOneWorker();

        // Lightweight autoscaler loop
        try
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                var q = CurrentQueueSize;
                var workers = CurrentWorkers;

                // Scale up if backlog is building
                if (q > 2 * _batchSize && workers < _maxWorkers)
                    StartOneWorker();

                // Scale down if idle and above min
                if (q == 0 && workers > _minWorkers)
                    StopOneWorker();

                await Task.Delay(200, stoppingToken).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) { /* normal */ }

        // Shutdown: complete writer & stop workers
        _channel.Writer.TryComplete();

        foreach (var cts in _workerCts)
            cts.Cancel();

        try { await Task.WhenAll(_workers).ConfigureAwait(false); } catch { /* best effort */ }
    }

    private void StartOneWorker()
    {
        var cts = new CancellationTokenSource();
        _workerCts.Add(cts);
        var task = Task.Run(() => WorkerLoopAsync(cts.Token), cts.Token);
        _workers.Add(task);
        Interlocked.Increment(ref _currentWorkers);
        _logger.LogDebug("Started worker {Count}", CurrentWorkers);
    }

    private void StopOneWorker()
    {
        // Cancel the most recently added worker if any above min
        for (var i = _workerCts.Count - 1; i >= 0; i--)
        {
            if (CurrentWorkers <= _minWorkers) break;
            var cts = _workerCts[i];
            if (!cts.IsCancellationRequested)
            {
                cts.Cancel();
                _workerCts.RemoveAt(i);
                Interlocked.Decrement(ref _currentWorkers);
                _logger.LogDebug("Stopped worker {Count}", CurrentWorkers);
                break;
            }
        }
    }

    private async Task WorkerLoopAsync(CancellationToken ct)
    {
        var sender = Sender.New(_repository.ILPConnectionString);
        var reader = _channel.Reader;
        var buffer = new List<T>(_batchSize);
        var deadline = DateTime.UtcNow.AddMilliseconds(_batchTimeoutMs);

        try
        {
            while (await reader.WaitToReadAsync(ct).ConfigureAwait(false))
            {
                while (reader.TryRead(out var item))
                {
                    // Adjust queue-size approximation
                    Interlocked.Decrement(ref _currentQueueSize);

                    buffer.Add(item);

                    if (buffer.Count >= _batchSize)
                        await FlushAsync().ConfigureAwait(false);
                }

                // Time-based flush when channel temporarily empty
                if (DateTime.UtcNow >= deadline)
                    await FlushAsync().ConfigureAwait(false);
            }

            // Drain on completion
            await FlushAsync().ConfigureAwait(false);
        }
        catch (OperationCanceledException) { /* normal */ }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Worker crashed");
        }

        return;

        async Task FlushAsync()
        {
            if (buffer.Count == 0) { deadline = DateTime.UtcNow.AddMilliseconds(_batchTimeoutMs); return; }

            try
            {
                await _repository.InsertBatchAsync(sender, buffer, ct).ConfigureAwait(false);
            }
            catch (OperationCanceledException) { /* shutting down */ }
            catch (Exception ex)
            {
                // Don’t re-enqueue to avoid ordering cycles; log & drop
                _logger.LogError(ex, "Failed to persist batch of {Count}", buffer.Count);
            }
            finally
            {
                buffer.Clear();
                deadline = DateTime.UtcNow.AddMilliseconds(_batchTimeoutMs);
            }
        }
    }

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        _channel.Writer.TryComplete();
        foreach (var cts in _workerCts) cts.Cancel();
        await base.StopAsync(cancellationToken).ConfigureAwait(false);
    }

    public override void Dispose()
    {
        foreach (var cts in _workerCts) cts.Dispose();
        base.Dispose();
    }
}