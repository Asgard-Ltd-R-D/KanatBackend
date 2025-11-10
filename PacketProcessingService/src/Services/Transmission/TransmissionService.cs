using System.Collections.Concurrent;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs.Data;
using PacketProcessing.DTOs.Stream;
using PacketProcessing.Entities;
using PacketProcessing.Hubs;
using PacketProcessing.Utils.Constants;
using PacketProcessing.Utils.Enums;
using PacketProcessing.Utils.Parsers;

namespace PacketProcessing.Services.Transmission;

/// <summary>
/// Transmission service that observes packet streams and transmits matching packets to SignalR clients
/// Supports both real-time and playback modes with configurable sampling intervals
/// </summary>
public class TransmissionService : ITransmissionService
{
    #region Fields

    private readonly ILogger<TransmissionService> _logger;
    private readonly IHubContext<CustomHub> _hubContext;
    private readonly ConcurrentDictionary<string, string> _streamKeyToConnectionIdDict = new();
    private readonly ConcurrentDictionary<string, long?> _streamKeyToIntervalMsDict = new();
    private readonly ConcurrentDictionary<string, long> _streamKeyToLastSentMsDict = new();

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

        try
        {
            if (_streamKeyToConnectionIdDict.TryAdd(key, connectionId))
            {
                // Initialize interval to null (no sampling) for new stream registration
                _streamKeyToIntervalMsDict.TryAdd(key, null);
                _streamKeyToLastSentMsDict.TryAdd(key, 0);

                _logger.LogInformation(
                    "Client {ConnectionId} registered on stream {Key}, interval initialized (no sampling)",
                    connectionId, key);

                // Send success ACK
                await _hubContext.Clients.Client(connectionId).SendAsync(Constants.SIGNALR_ACK, 
                    new AckDto { 
                        OperationType = OperationType.RegisterToMethod, 
                        Message = request, 
                        Success = true 
                    });

                // If IntervalMs provided on registration, apply interval now
                if (request.IntervalMs.HasValue)
                {
                    _logger.LogInformation("Applying initial IntervalMs={IntervalMs} for {Key} after registration", request.IntervalMs, key);
                    await SetTimeIntervalAsync(key, request.IntervalMs.Value, connectionId);
                }
            }
            else
            {
                _logger.LogInformation("Client {ConnectionId} already registered on stream {Key}, updating interval if provided", connectionId, key);
                
                // If IntervalMs provided, update the existing interval
                if (request.IntervalMs.HasValue)
                {
                    _logger.LogInformation("Updating IntervalMs={IntervalMs} for existing stream {Key}", request.IntervalMs, key);
                    await SetTimeIntervalAsync(key, request.IntervalMs.Value, connectionId);
                }
                else
                {
                    // If IntervalMs not provided (null), remove interval (send instantly, no sampling)
                    _logger.LogInformation("Removing interval for existing stream {Key} (no sampling, instant transmission)", key);
                    await SetTimeIntervalAsync(key, 0, connectionId);
                }
                
                // Send success ACK even if already registered
                await _hubContext.Clients.Client(connectionId).SendAsync(Constants.SIGNALR_ACK, 
                    new AckDto { 
                        OperationType = OperationType.RegisterToMethod, 
                        Message = request, 
                        Success = true 
                    });
            }

            _logger.LogInformation("Sent ack to client {ConnectionId} for stream registration: {Key}", connectionId, key);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error during stream registration for client {ConnectionId} on stream {Key}", connectionId, key);
            
            // Send error ACK
            await _hubContext.Clients.Client(connectionId).SendAsync(Constants.SIGNALR_ACK, 
                new AckDto { 
                    OperationType = OperationType.RegisterToMethod, 
                    Message = request, 
                    Success = false 
                });
            
            throw;
        }
    }
    
    public async Task DeregisterStreamAsync(string subscriptionKey)
    {
        ArgumentNullException.ThrowIfNull(subscriptionKey);
        var toBeRemovedConnectionId = _streamKeyToConnectionIdDict.TryGetValue(subscriptionKey, out var connectionId) ? connectionId : null;
        
        try
        {
            if (toBeRemovedConnectionId == null)
            {
                _logger.LogWarning("Stream not found for deregistration: {Key}, ignoring deregistration", subscriptionKey);
                return;
            }

            if (_streamKeyToConnectionIdDict.TryRemove(subscriptionKey, out _))
            {
                _logger.LogInformation("Client {ConnectionId} unregistered from stream {Key}", toBeRemovedConnectionId, subscriptionKey);
            }
            else
            {
                _logger.LogWarning("Client {ConnectionId} not found for deregistration: {Key}, ignoring deregistration", toBeRemovedConnectionId, subscriptionKey);
            }

            // Remove interval tracking
            _streamKeyToIntervalMsDict.TryRemove(subscriptionKey, out _);
            _streamKeyToLastSentMsDict.TryRemove(subscriptionKey, out _);
            _logger.LogDebug("Removed interval tracking for stream {Key}", subscriptionKey);

            // Send success ACK
            await _hubContext.Clients.Client(toBeRemovedConnectionId).SendAsync(Constants.SIGNALR_ACK, 
                new AckDto { 
                    OperationType = OperationType.UnregisterFromMethod, 
                    Message = subscriptionKey, 
                    Success = true 
                });

            _logger.LogInformation("Sent ack to client {ConnectionId} for stream deregistration: {Key}", toBeRemovedConnectionId, subscriptionKey);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error during stream deregistration for client {ConnectionId} on stream {Key}", toBeRemovedConnectionId, subscriptionKey);
            
            // Send error ACK
            if (toBeRemovedConnectionId != null)
            {
                await _hubContext.Clients.Client(toBeRemovedConnectionId).SendAsync(Constants.SIGNALR_ACK, 
                    new AckDto { 
                        OperationType = OperationType.UnregisterFromMethod, 
                        Message = subscriptionKey, 
                        Success = false 
                    });
            }
            
            throw;
        }
    }

    public async Task SetTimeIntervalAsync(string subscriptionKey, int intervalMs, string connectionId)
    {
        ArgumentNullException.ThrowIfNull(connectionId);
        ArgumentNullException.ThrowIfNull(subscriptionKey);
        var key = subscriptionKey;

        try
        {
            if (!_streamKeyToConnectionIdDict.TryGetValue(key, out var existingConnectionId))
            {
                await _hubContext.Clients.Client(connectionId).SendAsync(Constants.SIGNALR_ACK, 
                    new AckDto { 
                        OperationType = OperationType.SetTimeInterval, 
                        Message = $"Error setting interval to {intervalMs} for subscription {key}, connection {connectionId} not found", 
                        Success = false 
                    });

                _logger.LogWarning("Subscription key not found for interval setting: {SubscriptionKey}, connection {ConnectionId} not found", key, connectionId);
                return;
            }

            // Handle interval: 0 means no sampling (null), otherwise validate >= 1
            if (intervalMs < 0)
            {
                await _hubContext.Clients.Client(connectionId).SendAsync(Constants.SIGNALR_ACK, 
                    new AckDto { 
                        OperationType = OperationType.SetTimeInterval, 
                        Message = $"Interval cannot be negative, got {intervalMs}", 
                        Success = false 
                    });

                _logger.LogWarning("Invalid interval {IntervalMs} for subscription {SubscriptionKey}", intervalMs, key);
                return;
            }

            // Set the interval: 0 means null (no sampling), otherwise use the value
            if (intervalMs == 0)
            {
                _streamKeyToIntervalMsDict[key] = null;
                _streamKeyToLastSentMsDict.TryRemove(key, out _);
                _logger.LogInformation("Removed sampling interval for subscription {SubscriptionKey} (no sampling)", key);
            }
            else
            {
                _streamKeyToIntervalMsDict[key] = intervalMs;
                _streamKeyToLastSentMsDict.TryAdd(key, 0);
                _logger.LogInformation("Set interval for subscription {SubscriptionKey} to {IntervalMs}ms", key, intervalMs);
            }

            // Send success ACK
            await _hubContext.Clients.Client(existingConnectionId).SendAsync(Constants.SIGNALR_ACK, 
                new AckDto { 
                    OperationType = OperationType.SetTimeInterval, 
                    Message = new { subscriptionKey = key, intervalMs }, 
                    Success = true 
                });

            _logger.LogInformation("Sent success ack to client {ConnectionId} for interval setting: {SubscriptionKey}, {IntervalMs} Ms", existingConnectionId, key, intervalMs);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error setting interval to {Interval} for subscription {SubscriptionKey}", intervalMs, key);

            await _hubContext.Clients.Client(connectionId).SendAsync(Constants.SIGNALR_ACK, 
                new AckDto { 
                    OperationType = OperationType.SetTimeInterval, 
                    Message = $"Error setting interval to {intervalMs} for subscription {key}, {ex.Message}",
                    Success = false 
                });

            _logger.LogInformation("Sent error ack to client {ConnectionId} for interval setting: {SubscriptionKey}", connectionId, key);
            throw;
        }
    }

    #region Private Helpers

    private async Task DecideToTransmitAsync(BasePacketEntity packet)
    {
        try
        {
            // Find the connection ID for the packet, if doesn't exist it means that the packet is not registered for any connection
            var subscriptionKey = packet.GetSubscriptionKey();
            var existingConnectionId = _streamKeyToConnectionIdDict.TryGetValue(subscriptionKey, out var connectionId) ? connectionId : null;
            if (existingConnectionId == null)
                return;

            // Check if there's a sampling interval for this subscription key
            var shouldTransmit = false;
            
            if (_streamKeyToIntervalMsDict.TryGetValue(subscriptionKey, out var intervalMs))
            {
                if (intervalMs == null)
                {
                    // No interval set, transmit all packets
                    shouldTransmit = true;
                }
                else
                {
                    // Interval exists, check if enough time has passed since last transmission
                    var currentMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                    var lastSentMs = _streamKeyToLastSentMsDict.GetOrAdd(subscriptionKey, 0);
                    var elapsed = currentMs - lastSentMs;
                    
                    if (elapsed >= intervalMs.Value)
                    {
                        shouldTransmit = true;
                        _streamKeyToLastSentMsDict[subscriptionKey] = currentMs;
                    }
                }
            }
            else
            {
                // No interval entry, transmit (shouldn't happen but handle gracefully)
                shouldTransmit = true;
            }

            if (!shouldTransmit)
                return;

            // Convert packet to PlainDataDto
            var plainData = PlainDataConverter.Convert(packet);
            if (plainData == null)
            {
                _logger.LogWarning("Failed to convert packet to PlainData");
                return;
            }
            
            await SendToClientPacketAsync(existingConnectionId, plainData);

            _logger.LogDebug(
                "Transmitted packet to client {ConnectionId}: {SubscriptionKey} at {Timestamp}",
                existingConnectionId,
                plainData.SubscriptionKey, plainData.Timestamp);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error Transmitting packet");
        }
    }

    private async Task SendToClientPacketAsync(string connectionId, PlainDataDto data)
    {
        try
        {
            await _hubContext.Clients.Client(connectionId).SendAsync(Constants.SIGNALR_ON_RECEIVE_PACKET, data);
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
        _streamKeyToIntervalMsDict.Clear();
        _streamKeyToLastSentMsDict.Clear();
        
        _logger.LogInformation("All clients unregistered from all streams ({Count} total)", count);
        return Task.CompletedTask;
    }

    public Task DeregisterFromAllStreamsAsync(string connectionId)
    {
        var keysToRemove = _streamKeyToConnectionIdDict
            .Where(kvp => kvp.Value == connectionId)
            .Select(kvp => kvp.Key)
            .ToList();
        
        foreach (var key in keysToRemove)
        {
            _streamKeyToConnectionIdDict.TryRemove(key, out _);
            _streamKeyToIntervalMsDict.TryRemove(key, out _);
            _streamKeyToLastSentMsDict.TryRemove(key, out _);
        }
        
        _logger.LogInformation("Client {ConnectionId} unregistered from all streams", connectionId);
        return Task.CompletedTask;
    }

    public ICollection<string> GetRegisteredStreamKeys(string connectionId)
    {
        return _streamKeyToConnectionIdDict
            .Where(kvp => kvp.Value == connectionId)
            .Select(kvp => kvp.Key)
            .ToList();
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
