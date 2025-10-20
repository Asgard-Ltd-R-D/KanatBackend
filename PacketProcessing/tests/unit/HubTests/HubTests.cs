using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.SignalR;
using Microsoft.AspNetCore.SignalR.Client;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using PacketProcessing.DTOs.Data;
using PacketProcessing.Hubs;
using Xunit;

namespace PacketProcessing.Tests.unit.HubTests;

public class HubTests : IAsyncLifetime
{
    private IHost _host = null!;
    private TestServer _server = null!;

    private sealed class TestClientHub : HubClient
    {
        public TestClientHub(Microsoft.Extensions.Logging.ILogger<HubClient> logger) : base(logger) { }
    }

    public async Task InitializeAsync()
    {
        var builder = Host.CreateDefaultBuilder()
            .ConfigureWebHost(webBuilder =>
            {
                webBuilder.UseTestServer();
                webBuilder.ConfigureServices(services =>
                {
                    services.AddLogging();
                    services.AddSignalR();
                });
                webBuilder.Configure(app =>
                {
                    app.UseRouting();
                    app.UseEndpoints(endpoints =>
                    {
                        endpoints.MapHub<TestClientHub>("/testhub");
                    });
                });
            });

        _host = await builder.StartAsync();
        _server = _host.GetTestServer();
    }

    public async Task DisposeAsync()
    {
        await _host.StopAsync();
        _server.Dispose();
        _host.Dispose();
    }

    [Fact]
    public async Task Hub_ShouldAcceptConnection()
    {
        var connection = new HubConnectionBuilder()
            .WithUrl("http://localhost/testhub", o => o.HttpMessageHandlerFactory = _ => _server.CreateHandler())
            .WithAutomaticReconnect()
            .Build();

        await connection.StartAsync();
        Assert.Equal(HubConnectionState.Connected, connection.State);
        await connection.DisposeAsync();
    }

    [Fact]
    public async Task Hub_TransmitDataAsync_ShouldBroadcastToClients()
    {
        var connection = new HubConnectionBuilder()
            .WithUrl("http://localhost/testhub", o => o.HttpMessageHandlerFactory = _ => _server.CreateHandler())
            .WithAutomaticReconnect()
            .Build();

        var tcs = new TaskCompletionSource<(string method, PlainDataDto data)>(TaskCreationOptions.RunContinuationsAsynchronously);
        connection.On<string, PlainDataDto>("OnReceive", (method, data) =>
        {
            tcs.TrySetResult((method, data));
        });

        await connection.StartAsync();

        var payload = new PlainDataDto { Timestamp = DateTime.UtcNow, Value = 42.0f };
        await connection.InvokeAsync("TransmitDataAsync", payload, "TestMethod");

        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var completed = await Task.WhenAny(tcs.Task, Task.Delay(Timeout.Infinite, cts.Token));
        Assert.True(ReferenceEquals(completed, tcs.Task), "Broadcast not received in time");

        var (methodName, data) = await tcs.Task;
        Assert.Equal("TestMethod", methodName);
        Assert.True(data.Timestamp <= DateTime.UtcNow.AddSeconds(1));
        Assert.Equal(42.0f, data.Value);

        await connection.DisposeAsync();
    }
}

