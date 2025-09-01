using System.Threading.Channels;

namespace PacketProcessing.SignalR;

public interface IProducer<in T>
{
    ValueTask ProduceAsync(T item, CancellationToken ct = default);
    bool TryProduce(T item);
}

public sealed class ChannelProducer<T> : IProducer<T>
{
    private readonly Channel<T> _channel;
    public ChannelProducer(Channel<T> channel) => _channel = channel;

    public ValueTask ProduceAsync(T item, CancellationToken ct = default)
        => _channel.Writer.WriteAsync(item, ct);

    public bool TryProduce(T item) => _channel.Writer.TryWrite(item);
}