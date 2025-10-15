using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs.Data;

namespace PacketProcessing.Hubs;

public class HubClient : Hub
{
    private readonly ILogger<HubClient> _logger;

    public HubClient(ILogger<HubClient> logger)
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

    public async Task TransmitDataAsync(PlainDataDto data, string methodName)
    {
        if (data == null)
        {
            _logger.LogWarning("Data is null, skipping transmission");
            return;
        }
        
        _logger.LogInformation("Transmitting data to {MethodName}", methodName);
        await Clients.All.SendAsync("OnReceive", methodName, data);
    }
}