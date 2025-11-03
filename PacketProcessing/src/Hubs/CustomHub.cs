using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs.Stream;
using PacketProcessing.Hubs.ConnectionManager;
using PacketProcessing.Services.Transmission;
using PacketProcessing.Utils.Constants;
using PacketProcessing.Utils.Enums;
using SignalRSwaggerGen.Attributes;

namespace PacketProcessing.Hubs;

/// <summary>
/// SignalR Hub for real-time packet data transmission and playback control
/// </summary>
[SignalRHub("/hubs/packets")]
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
        try
        {
            ArgumentNullException.ThrowIfNull(Context.ConnectionId);
            _logger.LogInformation("Client {ConnectionId} performing connection to hub", Context.ConnectionId);
            _connectionManager.Add(Context.ConnectionId);
            _logger.LogInformation("Mapped ConnectionId {ConnectionId} to hub", Context.ConnectionId);
            await base.OnConnectedAsync();
            
            // Get all active streams for this connection and send ACK list
            var activeStreamKeys = _transmissionService.GetRegisteredStreamKeys(Context.ConnectionId);
            var ackList = activeStreamKeys.Select(key => new AckDto 
            { 
                OperationType = OperationType.ConnectionEstablished, 
                Message = key, 
                Success = true 
            }).ToList();
            
            await Clients.Client(Context.ConnectionId).SendAsync(Constants.SIGNALR_ACK, ackList);
            _logger.LogInformation("Sent ACK list with {Count} active streams to client {ConnectionId}", ackList.Count, Context.ConnectionId);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error connecting to hub");
            await Clients.Client(Context.ConnectionId).SendAsync(Constants.SIGNALR_ACK, new AckDto { OperationType = OperationType.ConnectionEstablished, Success = false, Message = ex.Message });
        }
    }

    /// <summary>
    /// Called when a client disconnects from the hub.
    /// Removes the mapping between user ID and connection ID.
    /// </summary>
    /// <param name="exception">The exception that caused the disconnection, if any.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    public override async Task OnDisconnectedAsync(Exception? exception)
    {
        try
        {   
            ArgumentNullException.ThrowIfNull(Context.ConnectionId);
            _logger.LogInformation("Client {ConnectionId} performing disconnection from hub", Context.ConnectionId);
            _connectionManager.Remove(Context.ConnectionId);
            await _transmissionService.DeregisterFromAllStreamsAsync(Context.ConnectionId); // Deregister from all streams that the client is registered to
            _logger.LogInformation("Removed mapping for ConnectionId {ConnectionId}", Context.ConnectionId);
            await base.OnDisconnectedAsync(exception);
            
            // Send ACK with null message on disconnect
            await Clients.Client(Context.ConnectionId).SendAsync(Constants.SIGNALR_ACK, new AckDto { OperationType = OperationType.ConnectionClosed, Success = true, Message = null });
            _logger.LogInformation("Sent disconnect ACK with null message to client {ConnectionId}", Context.ConnectionId);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error disconnecting from hub");
            await Clients.Client(Context.ConnectionId).SendAsync(Constants.SIGNALR_ACK, new AckDto { OperationType = OperationType.ConnectionClosed, Success = false, Message = ex.Message });
        }
    }

    public async Task RegisterToMethod(StreamRequestDto requestStream)
    {
        try
        {
            ArgumentNullException.ThrowIfNull(requestStream.SubscriptionKey);
            _logger.LogInformation("Client {ConnectionId} performing registration to method {SubscriptionKey}", Context.ConnectionId, requestStream.SubscriptionKey);
            await _transmissionService.RegisterStreamAsync(requestStream, Context.ConnectionId);
            _logger.LogInformation("Client {ConnectionId} registered to method {SubscriptionKey}", Context.ConnectionId, requestStream.SubscriptionKey);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error registering to method {SubscriptionKey}", requestStream.SubscriptionKey);
            throw;
        }
    }

    public async Task UnregisterFromMethod(string subscriptionKey)
    {
        try 
        {
            ArgumentNullException.ThrowIfNull(subscriptionKey);
            _logger.LogInformation("Client {ConnectionId} is unregistering from method {SubscriptionKey}", Context.ConnectionId, subscriptionKey);
            await _transmissionService.DeregisterStreamAsync(subscriptionKey);
            _logger.LogInformation("Client {ConnectionId} is unregistered from method {SubscriptionKey}", Context.ConnectionId, subscriptionKey);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error unregistering from method {SubscriptionKey}", subscriptionKey);
            throw;
        }
    }

    /// <summary>
    /// Sets a sampling interval for a specific stream.
    /// Packets for this stream will only be transmitted if the specified interval (in milliseconds) has elapsed since the last transmission.
    /// Setting intervalMs to 0 will disable sampling for the stream.
    /// </summary>
    /// <param name="request">The interval request DTO containing the subscription key and interval in milliseconds.</param>
    public async Task SetTimeInterval(IntervalRequestDto request)
    {
        try
        {
            ArgumentNullException.ThrowIfNull(request);
            _logger.LogInformation("Client {ConnectionId} is setting interval to {Interval} for subscription {SubscriptionKey}", Context.ConnectionId, request.IntervalMs, request.SubscriptionKey);
            await _transmissionService.SetTimeIntervalAsync(request, Context.ConnectionId);
            _logger.LogInformation("Client {ConnectionId} set interval to {Interval} for subscription {SubscriptionKey}", Context.ConnectionId, request.IntervalMs, request.SubscriptionKey);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error setting interval to {Interval} for subscription {SubscriptionKey}", request.IntervalMs, request.SubscriptionKey);
            throw;
        }
    }

    public Task ReceiveHitDetectionData()
    {
        //TODO: Implement on version 2.0
        throw new NotImplementedException();
    }
}