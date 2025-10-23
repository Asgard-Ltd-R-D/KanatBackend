using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs.Stream;
using PacketProcessing.Hubs.ConnectionManager;
using PacketProcessing.Services.Transmission;
using SignalRSwaggerGen.Attributes;

namespace PacketProcessing.Hubs;

/// <summary>
/// SignalR Hub for real-time packet data transmission and playback control
/// </summary>
[SignalRHub]
public class CustomHub : Hub
{
    private readonly ILogger<CustomHub> _logger;
    private readonly IConnectionManager _connectionManager;
    private readonly ITransmissionService _transmissionService;
    public CustomHub(ILogger<CustomHub> logger, IConnectionManager connectionManager, ITransmissionService transmissionService)
    {
        _logger = logger;
        _connectionManager = connectionManager;
        _transmissionService = transmissionService;
    }

    /// <summary>
    /// Called when a client connects to the hub.
    /// Maps the user ID to the connection ID and stores the connection.
    /// </summary>
    /// <returns>A task that represents the asynchronous operation.</returns>
    public override async Task OnConnectedAsync()
    {
        _logger.LogInformation("Client {ConnectionId} performing connection to hub", Context.ConnectionId);
        _connectionManager.Add(Context.ConnectionId);
        _logger.LogInformation("Mapped ConnectionId {ConnectionId} to hub", Context.ConnectionId);
        await base.OnConnectedAsync();
    }

    /// <summary>
    /// Called when a client disconnects from the hub.
    /// Removes the mapping between user ID and connection ID.
    /// </summary>
    /// <param name="exception">The exception that caused the disconnection, if any.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    public override async Task OnDisconnectedAsync(Exception? exception)
    {
        _logger.LogInformation("Client {ConnectionId} performing disconnection from hub", Context.ConnectionId);
        _connectionManager.Remove(Context.ConnectionId);
        await _transmissionService.DeregisterFromAllStreamsAsync(Context.ConnectionId); // Deregister from all streams that the client is registered to
        _logger.LogInformation("Removed mapping for ConnectionId {ConnectionId}", Context.ConnectionId);
        await base.OnDisconnectedAsync(exception);
    }

    public async Task RegisterToMethod(StreamRequestDto requestStream)
    {
        _logger.LogInformation("Client {ConnectionId} performing registration to method {SubscriptionKey}", Context.ConnectionId, requestStream.SubscriptionKey);
        await _transmissionService.RegisterStreamAsync(requestStream, Context.ConnectionId);
        _logger.LogInformation("Client {ConnectionId} registered to method {SubscriptionKey}", Context.ConnectionId, requestStream.SubscriptionKey);
    }

    public async Task UnregisterFromMethod(StreamRequestDto requestStream)
    {
        _logger.LogInformation("Client {ConnectionId} is unregistering from method {SubscriptionKey}", Context.ConnectionId, requestStream.SubscriptionKey);
        await _transmissionService.DeregisterStreamAsync(requestStream);
        _logger.LogInformation("Client {ConnectionId} is unregistered from method {SubscriptionKey}", Context.ConnectionId, requestStream.SubscriptionKey);
    }

    public async Task ReceiveHitDetectionData()
    {
        //TODO: Implement on version 2.0
        throw new NotImplementedException();
    }
}