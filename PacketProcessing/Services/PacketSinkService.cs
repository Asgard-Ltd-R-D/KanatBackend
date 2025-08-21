using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using PacketProcessing.Config;
using PacketProcessing.Repositories;

namespace PacketProcessing.Services;

public interface IPacketSink<TPacket>
{
    ValueTask EnqueueAsync(TPacket packet, CancellationToken ct = default);
    bool TryEnqueue(TPacket packet);
}

public sealed class PacketPipelineService<TPacket> : BackgroundService, IPacketSink<TPacket>
    where TPacket : class
{
    private readonly IRepository<TPacket> _repository;
    private readonly IRealtimeClient<TPacket> _realtime;
    private readonly ILogger<PacketPipelineService<TPacket>> _logger;
    
    protected readonly ApplicationOptions.ChannelOptions _channelOptions;
    protected readonly ApplicationOptions.WorkerOptions _workerOptions;

    private readonly Channel<TPacket> _channel;
    private readonly List<Task> _workers = new();

    public PacketPipelineService(
        IRepository<TPacket> repository,
        IRealtimeClient<TPacket> realtime,
        IOptions<BatchOptions> opt,
        ILogger<PacketPipelineService<TPacket>> logger)
    {
        _repository = repository;
        _realtime = realtime;
        _logger = logger;
        _opt = opt.Value;

        var chOpts = new BoundedChannelOptions(_opt.ChannelCapacity)
        {
            FullMode = BoundedChannelFullMode.Wait,
            SingleWriter = false,
            SingleReader = false
        };
        _channel = Channel.CreateBounded<TPacket>(chOpts);
    }

    public ValueTask EnqueueAsync(TPacket packet, CancellationToken ct = default)
        => _channel.Writer.WriteAsync(packet, ct);

    public bool TryEnqueue(TPacket packet)
        => _channel.Writer.TryWrite(packet);

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        try
        {
            for (int i = 0; i < Math.Max(1, _opt.Workers); i++)
                _workers.Add(Task.Run(() => WorkerLoopAsync(stoppingToken), stoppingToken));

            await Task.WhenAll(_workers);
        }
        catch (OperationCanceledException) { /* normal on shutdown */ }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Packet pipeline {Type} crashed", typeof(TPacket).Name);
        }
    }

    private async Task WorkerLoopAsync(CancellationToken ct)
    {
        var reader = _channel.Reader;
        var buffer = new List<TPacket>(_opt.MaxBatchSize);
        int approxBytes = 0;
        var deadline = DateTime.UtcNow + _opt.MaxBatchAge;

        static int EstimateBytes(TPacket p)
        {
            // If your TPacket exposes Payload.Length, use it here.
            // Fallback heuristic:
            return 256;
        }

        async Task FlushAsync()
        {
            if (buffer.Count == 0) return;

            try
            {
                // Storage first (durable)
                await _repository.AddBatchAsync(buffer, ct);

                // Realtime next (best-effort)
                try { await _realtime.SendBatchAsync(buffer, ct); }
                catch (Exception ex) { _logger.LogDebug(ex, "Realtime batch send failed ({Count})", buffer.Count); }
            }
            finally
            {
                buffer.Clear();
                approxBytes = 0;
                deadline = DateTime.UtcNow + _opt.MaxBatchAge;
            }
        }

        while (await reader.WaitToReadAsync(ct))
        {
            while (reader.TryRead(out var item))
            {
                // Optional ultra-low-latency realtime path
                if (_opt.RealtimePerItem)
                {
                    // Fire-and-forget, don’t block the hot path
                    _ = _realtime.SendAsync(item, ct).AsTask().ContinueWith(
                        t => { if (t.Exception != null) _logger.LogDebug(t.Exception, "Realtime send failed"); },
                        TaskScheduler.Default);
                }

                buffer.Add(item);
                approxBytes += EstimateBytes(item);

                if (buffer.Count >= _opt.MaxBatchSize || approxBytes >= _opt.MaxBatchBytes)
                    await FlushAsync();
            }

            if (DateTime.UtcNow >= deadline)
                await FlushAsync();
        }

        await FlushAsync();
    }

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        _channel.Writer.TryComplete();
        await base.StopAsync(cancellationToken);
    }
}