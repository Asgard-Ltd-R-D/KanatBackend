using System.Collections.Concurrent;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs.Data;
using PacketProcessing.DTOs.Stream;
using PacketProcessing.Entities;
using PacketProcessing.Hubs;
using PacketProcessing.Utils.Constants;
using PacketProcessing.Utils.Parsers;

namespace PacketProcessing.Services.Transmission;

/// <summary>
/// Transmission service that observes packet streams and transmits matching packets to SignalR clients
/// Supports both real-time and playback modes
/// </summary>
public class TransmissionService : ITransmissionService
{
    #region Fields

    private readonly ILogger<TransmissionService> _logger;
    private readonly IHubContext<CustomHub> _hubContext;
    private readonly ConcurrentDictionary<string, string> _streamKeyToConnectionIdDict = new();


    #endregion

    #region Constructor
    
    public TransmissionService(ILogger<TransmissionService> logger, IHubContext<CustomHub> hubContext)
    {
        _logger = logger;
        _hubContext = hubContext;
    }

    #endregion

    #region Public API

    public async Task RegisterStreamAsync(StreamRequestDto request, string connectionId)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(connectionId);

        var key = request.SubscriptionKey;

        if (_streamKeyToConnectionIdDict.TryAdd(key, connectionId))
        {
            _logger.LogInformation(
                "Client {ConnectionId} registered on stream {Key}",
                connectionId, key);
        }
        else
        {
            _logger.LogInformation("Client {ConnectionId} already registered on stream {Key}, ignoring registration", connectionId, key);
        }
        await _hubContext.Clients.Client(connectionId).SendAsync(Constants.SIGNALR_ACK, request);

        _logger.LogInformation("Sent ack to client {ConnectionId} for stream registration: {Key}", connectionId, key);

    }
    
    public async Task DeregisterStreamAsync(StreamRequestDto request)
    {
        ArgumentNullException.ThrowIfNull(request);

        var key = request.SubscriptionKey;
        var toBeRemovedConnectionId = _streamKeyToConnectionIdDict.TryGetValue(key, out var connectionId) ? connectionId : null;
        if (toBeRemovedConnectionId == null)
        {
            _logger.LogWarning("Stream not found for deregistration: {Key}, ignoring deregistration", key);
            return;
        }

        if (_streamKeyToConnectionIdDict.TryRemove(key, out _))
        {
            _logger.LogInformation("Client {ConnectionId} unregistered from stream {Key}", toBeRemovedConnectionId, key);
        }
        else
        {
            _logger.LogWarning("Client {ConnectionId} not found for deregistration: {Key}, ignoring deregistration", toBeRemovedConnectionId, key);
        }

        await _hubContext.Clients.Client(toBeRemovedConnectionId).SendAsync(Constants.SIGNALR_ACK, request);

        _logger.LogInformation("Sent ack to client {ConnectionId} for stream deregistration: {Key}", toBeRemovedConnectionId, key);
    }

    #region Private Helpers

    private async Task DecideToTransmitAsync(BasePacketEntity packet)
    {
        try
        {
            // Find the connection ID for the packet, if doesn't exist it means that the packet is not registered for any connection
            var existingConnectionId = _streamKeyToConnectionIdDict.TryGetValue(packet.GetSubscriptionKey(), out var connectionId) ? connectionId : null;
            if (existingConnectionId == null)
                return;


            // Convert packet to PlainDataDto
            var plainData = PlainDataConverter.Convert(packet);
            if (plainData == null)
            {
                _logger.LogWarning("Failed to convert packet to PlainData");
                return;
            }
            await SendToClientPacketAsync(existingConnectionId, Constants.SIGNALR_ON_RECEIVE_PACKET, plainData);

            _logger.LogDebug(
                "Transmitted packet to client {ConnectionId}: {DataPipe}.{Method} at {Timestamp}",
                existingConnectionId,
                plainData.DataPipe, plainData.MethodName, plainData.Timestamp);
    }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error Transmitting packet");
        }
    }

    private async Task SendToClientPacketAsync(string connectionId, string methodName, PlainDataDto data)
    {
        try
        {
            await _hubContext.Clients.Client(connectionId).SendAsync(methodName, data);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error sending to SignalR clients");
        }
    }

    #endregion

    public Task UnregisterAllStreamsAsync()
    {
        var count = _streamKeyToConnectionIdDict.Count;
        _streamKeyToConnectionIdDict.Clear();
        _logger.LogInformation("All clients unregistered from all streams ({Count} total)", count);
        return Task.CompletedTask;
    }

    public Task DeregisterFromAllStreamsAsync(string connectionId)
    {
        _streamKeyToConnectionIdDict.Where(kvp => kvp.Value == connectionId).ToList().ForEach(kvp => _streamKeyToConnectionIdDict.TryRemove(kvp.Key, out _));
        _logger.LogInformation("Client {ConnectionId} unregistered from all streams", connectionId);
        return Task.CompletedTask;
    }

    public ICollection<StreamRequestDto> GetRegisteredStreams()
    {
        throw new NotImplementedException();
    }

    #endregion

    #region IObserver Implementations

    public void OnNext(BasePacketEntity packet)
        => DecideToTransmitAsync(packet).GetAwaiter().GetResult();

    public void OnError(Exception error)
        => _logger.LogError(error, "Error in packet stream");

    public void OnCompleted()
        => _logger.LogInformation("Packet stream completed");


    #endregion
}
