using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.DependencyInjection;
using PacketProcessing.DTOs;

namespace PacketProcessing.Telemetry;

/// <summary>
/// SignalR Hub for real-time telemetry data transmission
/// Access restricted to localhost only for security
/// </summary>
public class TelemetryHub : Hub
{
    private readonly ILogger<TelemetryHub> _logger;
    private readonly IServiceProvider _serviceProvider;

    public TelemetryHub(ILogger<TelemetryHub> logger, IServiceProvider serviceProvider)
    {
        _logger = logger;
        _serviceProvider = serviceProvider;
    }

    /// <summary>
    /// Called when a client connects to the hub
    /// </summary>
    public override async Task OnConnectedAsync()
    {
        var remoteIp = Context.GetHttpContext()?.Connection?.RemoteIpAddress;
        _logger.LogInformation("Client {ConnectionId} connected to TelemetryHub from IP: {RemoteIp}", Context.ConnectionId, remoteIp);
        
        // Send initial telemetry data to the newly connected client
        try
        {
            using var scope = _serviceProvider.CreateScope();
            var telemetryService = scope.ServiceProvider.GetService<ITelemetryService>();
            if (telemetryService != null)
            {
                var initialTelemetry = await telemetryService.SnapshotAsync();
                await Clients.Caller.SendAsync("telemetry:update", initialTelemetry);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to send initial telemetry data to client {ConnectionId}", Context.ConnectionId);
        }
        
        await base.OnConnectedAsync();
    }

    /// <summary>
    /// Called when a client disconnects from the hub
    /// </summary>
    public override async Task OnDisconnectedAsync(Exception? exception)
    {
        _logger.LogInformation("Client {ConnectionId} disconnected from TelemetryHub", Context.ConnectionId);
        await base.OnDisconnectedAsync(exception);
    }
}
