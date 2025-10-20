using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs.Data;

namespace PacketProcessing.Hubs;

/// <summary>
/// SignalR Hub for real-time packet data transmission
/// </summary>
public class PacketHub : Hub
{
    private readonly ILogger<PacketHub> _logger;

    public PacketHub(ILogger<PacketHub> logger)
    {
        _logger = logger;
    }

    public override async Task OnConnectedAsync()
    {
        _logger.LogInformation("Client connected: {ConnectionId}", Context.ConnectionId);
        await base.OnConnectedAsync();
    }

    public override async Task OnDisconnectedAsync(Exception? exception)
    {
        _logger.LogInformation("Client disconnected: {ConnectionId}", Context.ConnectionId);
        await base.OnDisconnectedAsync(exception);
    }
}

/// <summary>
/// Service for transmitting packet data to connected SignalR clients
/// </summary>
public class HubClient
{
    private readonly IHubContext<PacketHub> _hubContext;
    private readonly ILogger<HubClient> _logger;

    public HubClient(IHubContext<PacketHub> hubContext, ILogger<HubClient> logger)
    {
        _hubContext = hubContext;
        _logger = logger;
    }

    public async Task TransmitDataAsync(PlainDataDto data, string methodName)
    {
        if (data == null)
        {
            _logger.LogWarning("Data is null, skipping transmission");
            return;
        }
        
        try
        {
            await _hubContext.Clients.All.SendAsync("OnReceive", methodName, data);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to transmit data to {MethodName}", methodName);
        }
    }
}