using System.Threading.Channels;

namespace PacketProcessing.SignalR;

public interface IConsumer<out T>
{
    IAsyncEnumerable<T> ReadAllAsync(CancellationToken ct = default);
}

public sealed class ChannelConsumer<T> : IConsumer<T>
{
    private readonly Channel<T> _channel;
    public ChannelConsumer(Channel<T> channel) => _channel = channel;

    public async IAsyncEnumerable<T> ReadAllAsync([System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct = default)
    {
        while (await _channel.Reader.WaitToReadAsync(ct).ConfigureAwait(false))
        {
            while (_channel.Reader.TryRead(out var item))
                yield return item;
        }
    }
}