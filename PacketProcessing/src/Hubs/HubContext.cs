using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;
using PacketProcessing.Services.Playback;

namespace PacketProcessing.Hubs;

/// <summary>
/// SignalR Hub for real-time packet data transmission and playback control
/// </summary>
public class HubContext : Hub
{
    private readonly ILogger<HubContext> _logger;

    public HubContext(ILogger<HubContext> logger, IPlaybackService playbackService)
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