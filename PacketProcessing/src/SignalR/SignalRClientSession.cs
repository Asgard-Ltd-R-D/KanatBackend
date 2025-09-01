using System.Threading.Channels;
using Microsoft.AspNetCore.SignalR.Client;

namespace PacketProcessing.SignalR;

public sealed class SignalRClientSession : IAsyncDisposable
{
    private readonly IHubClientHost _host;
    private readonly List<IAsyncDisposable> _registrations = new();
    private readonly CancellationTokenSource _cts = new();

    public SignalRClientSession(IHubClientHost host) => _host = host;

    public IProducer<TOut> AttachProducer<TOut>(
        Func<HubConnection, TOut, CancellationToken, Task> sendAsync)
    {
        ArgumentNullException.ThrowIfNull(sendAsync);

        // bounded, sensible defaults without exposing settings
        var ch = Channel.CreateBounded<TOut>(new BoundedChannelOptions(1024)
        {
            FullMode = BoundedChannelFullMode.Wait,
            SingleReader = true,
            SingleWriter = false
        });

        var producer = new ChannelProducer<TOut>(ch);

        var loop = Task.Run(async () =>
        {
            try
            {
                var hub = _host.Connection;
                while (await ch.Reader.WaitToReadAsync(_cts.Token).ConfigureAwait(false))
                {
                    while (ch.Reader.TryRead(out var item))
                        await sendAsync(hub, item, _cts.Token).ConfigureAwait(false);
                }
            }
            catch (OperationCanceledException) { }
        }, _cts.Token);

        _registrations.Add(AsyncDispose.Create(async () =>
        {
            ch.Writer.TryComplete();
            await loop.ConfigureAwait(false);
        }));

        return producer;
    }

    public IConsumer<TIn> AttachConsumer<TIn>(
        Action<HubConnection, ChannelWriter<TIn>> registerIncoming)
    {
        if (registerIncoming is null) throw new ArgumentNullException(nameof(registerIncoming));

        var ch = Channel.CreateBounded<TIn>(new BoundedChannelOptions(1024)
        {
            FullMode = BoundedChannelFullMode.DropOldest,
            SingleReader = false,
            SingleWriter = true
        });

        // bind server->client handler(s)
        registerIncoming(_host.Connection, ch.Writer);

        var consumer = new ChannelConsumer<TIn>(ch);

        _registrations.Add(AsyncDispose.Create(() =>
        {
            ch.Writer.TryComplete();
            return Task.CompletedTask;
        }));

        return consumer;
    }

    public Task StartAsync(CancellationToken ct = default) => _host.EnsureStartedAsync(ct);

    public async ValueTask DisposeAsync()
    {
        _cts.Cancel();
        foreach (var reg in _registrations)
            await reg.DisposeAsync().ConfigureAwait(false);
        _cts.Dispose();
    }

    private sealed class AsyncDispose : IAsyncDisposable
    {
        private readonly Func<Task> _dispose;
        private AsyncDispose(Func<Task> dispose) => _dispose = dispose;
        public static IAsyncDisposable Create(Func<Task> d) => new AsyncDispose(d);
        public ValueTask DisposeAsync() => new(_dispose());
    }
}

// Example usage:
/*

    public sealed record ChatOut(string Room, string User, string Text);
    public sealed record ChatIn(string Room, string User, string Text, DateTimeOffset SentAt);

    public sealed record MetricOut(string Name, double Value, long UnixNs);
    public sealed record MetricIn(string Name, double Value, DateTimeOffset ServerTime);

    // Usage
    public sealed class MyFeature
    {
        private readonly SignalRClientSession _session;

        public IProducer<ChatOut> ChatProducer { get; }
        public IConsumer<ChatIn>  ChatConsumer  { get; }

        public IProducer<MetricOut> MetricProducer { get; }
        public IConsumer<MetricIn>  MetricConsumer  { get; }

        public MyFeature(IHubClientHost host)
        {
            _session = new SignalRClientSession(host);

            // Incoming metrics
            MetricConsumer = _session.AttachConsumer<MetricIn>(
                (hub, writer) =>
                    hub.On<string, double, DateTimeOffset>("MetricAck",
                        (name, value, ts) => writer.TryWrite(new MetricIn(name, value, ts))));

            // Incoming chat
            ChatConsumer = _session.AttachConsumer<ChatIn>(
                (hub, writer) =>
                    hub.On<string, string, string, DateTimeOffset>("ReceiveMessage",
                        (room, user, text, ts) => writer.TryWrite(new ChatIn(room, user, text, ts))));

            // Outgoing metrics
            MetricProducer = _session.AttachProducer<MetricOut>(
                (hub, m, ct) => hub.InvokeAsync("SendMetric", m.Name, m.Value, m.UnixNs, ct));

            // Outgoing chat
            ChatProducer = _session.AttachProducer<ChatOut>(
                (hub, m, ct) => hub.InvokeAsync("SendMessage", m.Room, m.User, m.Text, ct));
        }

        public Task StartAsync(CancellationToken ct = default) => _session.StartAsync(ct);
    }

*/