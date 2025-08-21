using System.Threading.Channels;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using PacketProcessing.Config;
using PacketProcessing.Repositories;

namespace PacketProcessing.Services;

public interface IPacketSink<T>
{
    ValueTask EnqueueAsync(T packet, CancellationToken ct = default);
    bool TryEnqueue(T packet);
}

public sealed class PacketPipelineService<T> : BackgroundService, IPacketSink<T>
    where T : class
{
    private readonly IRepository<T> _repository;
    private readonly ILogger<PacketPipelineService<T>> _logger;
    
    protected readonly ApplicationOptions.ChannelOptions _channelOptions;
    protected readonly ApplicationOptions.WorkerOptions _workerOptions;
    protected readonly ApplicationOptions.DbOptions _dbOptions;

    private readonly Channel<T> _channel;
    private readonly List<Task> _workers = [];

    public PacketPipelineService(
        IRepository<T> repository,
        IOptions<ApplicationOptions.ChannelOptions> channelOptions,
        IOptions<ApplicationOptions.WorkerOptions> workerOptions,
        IOptions<ApplicationOptions.DbOptions> dbOptions,
        ILogger<PacketPipelineService<T>> logger)
    {
        _repository = repository;
        _logger = logger;
        _channelOptions = channelOptions.Value;
        _workerOptions = workerOptions.Value;
        _dbOptions = dbOptions.Value;

        var chOpts = new BoundedChannelOptions(_channelOptions.Capacity)
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
            for (int i = 0; i < Math.Max(1, _workerOptions.MinWorkers); i++)
                _workers.Add(Task.Run(() => WorkerLoopAsync(stoppingToken), stoppingToken));

            await Task.WhenAll(_workers);
        }
        catch (OperationCanceledException) { /* normal on shutdown */ }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Packet pipeline {Type} crashed", typeof(T).Name);
        }
    }

    private async Task WorkerLoopAsync(CancellationToken ct)
    {
        var reader = _channel.Reader;
        var buffer = new List<T>(_dbOptions.BatchSize);
        int approxBytes = 0;
        var deadline = DateTime.UtcNow.Millisecond + _dbOptions.BatchTimeoutMs;

        static int EstimateBytes(T p)
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
                await _repository.InsertBatchAsync(buffer, ct);
            }
            finally
            {
                buffer.Clear();
                approxBytes = 0;
                deadline = DateTime.UtcNow.Millisecond + _dbOptions.BatchTimeoutMs;
            }
        }

        while (await reader.WaitToReadAsync(ct))
        {
            while (reader.TryRead(out var item))
            {
                buffer.Add(item);
                approxBytes += EstimateBytes(item);

                if (buffer.Count >= _dbOptions.BatchSize)
                    await FlushAsync();
            }

            if (DateTime.UtcNow.Millisecond >= deadline)
                await FlushAsync();
        }

        await FlushAsync();
    }

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        _channel.Writer.TryComplete();
        await base.StopAsync(cancellationToken);
    }

    public ValueTask EnqueueAsync(T packet, CancellationToken ct = default)
    {
        throw new NotImplementedException();
    }

    public bool TryEnqueue(T packet)
    {
        throw new NotImplementedException();
    }
}