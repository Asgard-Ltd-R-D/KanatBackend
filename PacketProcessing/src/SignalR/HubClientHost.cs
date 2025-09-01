using Microsoft.AspNetCore.SignalR.Client;

namespace PacketProcessing.SignalR;

public interface IHubClientHost
{
    HubConnection Connection { get; }
    Task EnsureStartedAsync(CancellationToken ct = default);
}

public sealed class HubClientHost : IHubClientHost, IAsyncDisposable
{
    private readonly SemaphoreSlim _gate = new(1,1);
    public HubConnection Connection { get; }

    public HubClientHost(string hubUrl, IRetryPolicy? retryPolicy = null)
    {
        Connection = new HubConnectionBuilder()
            .WithUrl(hubUrl)
            .WithAutomaticReconnect(retryPolicy ?? new DefaultRetryPolicy())
            .Build();
    }

    public async Task EnsureStartedAsync(CancellationToken ct = default)
    {
        if (Connection.State == HubConnectionState.Connected) return;
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            if (Connection.State != HubConnectionState.Connected)
                await Connection.StartAsync(ct).ConfigureAwait(false);
        }
        finally { _gate.Release(); }
    }

    public async ValueTask DisposeAsync()
    {
        try { await Connection.DisposeAsync(); } catch { /* ignore */ }
        _gate.Dispose();
    }

    private sealed class DefaultRetryPolicy : IRetryPolicy
    {
        public TimeSpan? NextRetryDelay(RetryContext c) =>
            c.PreviousRetryCount switch { 0 => TimeSpan.Zero, 1 => TimeSpan.FromSeconds(2),
                                          2 => TimeSpan.FromSeconds(5), 3 => TimeSpan.FromSeconds(10),
                                          4 => TimeSpan.FromSeconds(30), _ => TimeSpan.FromMinutes(1) };
    }
}