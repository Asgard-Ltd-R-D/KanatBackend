using System.Collections.Concurrent;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs.Data;
using PacketProcessing.DTOs.Stream;
using PacketProcessing.Entities;
using PacketProcessing.Entities.Packet;
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
    private readonly IHubContext<HubContext> _hubContext;

    private readonly ConcurrentDictionary<string, StreamRequest> _registeredStreams = new();

    #endregion

    #region Constructor
    
    public TransmissionService(ILogger<TransmissionService> logger, IHubContext<HubContext> hubContext)
    {
        _logger = logger;
        _hubContext = hubContext;
    }

    #endregion

    #region Public API

    public Task RegisterStreamAsync(StreamRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        var key = request.SubscriptionKey;

        if (_registeredStreams.TryAdd(key, request))
        {
            var mode = request.IsPlayback ? "Playback" : "Realtime";
            _logger.LogInformation(
                "{Mode} stream registered: {Key} [{DataPipe}.{Method}]",
                mode, key, request.DataPipe, request.MethodName);
        }
        else
        {
            _logger.LogWarning("Stream already registered: {Key}", key);
        }

        return Task.CompletedTask;
    }

        #region Private Helpers

    private async Task ProcessPacketAsync(BasePacketEntity packet)
    {
        try
        {
            // Find all matching stream requests
            var matchingStreams = _registeredStreams.Values
                .Where(stream => stream.MatchesPacket(packet))
                .ToList();

            if (matchingStreams.Count == 0)
                return;

            // Convert packet to PlainDataDto
            var plainData = PlainDataConverter.Convert(packet);
            if (plainData == null)
            {
                _logger.LogWarning("Failed to convert packet to PlainData");
                return;
            }

            // Send to SignalR for each matching stream
            foreach (var stream in matchingStreams)
            {
                var data = new PlainDataDto
                {
                    Timestamp = plainData.Timestamp,
                    Value = plainData.Value,
                    DataPipe = stream.DataPipe,
                    MethodName = packet.Description
                };

                var methodName = stream.IsPlayback 
                    ? Constants.PLAYBACK_METHOD_NAME 
                    : Constants.REALTIME_METHOD_NAME;

                await SendToClientsAsync(methodName, data);

                _logger.LogDebug(
                    "Transmitted {Mode} packet: {DataPipe}.{Method} at {Timestamp}",
                    stream.IsPlayback ? "Playback" : "Realtime",
                    data.DataPipe, data.MethodName, data.Timestamp);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error processing packet");
        }
    }

    private async Task SendToClientsAsync(string methodName, PlainDataDto data)
    {
        try
        {
            await _hubContext.Clients.All.SendAsync(methodName, data);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error sending to SignalR clients");
        }
    }

    #endregion

    public Task UnregisterStreamAsync(StreamRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        var key = request.SubscriptionKey;

        if (_registeredStreams.TryRemove(key, out _))
        {
            _logger.LogInformation("Stream unregistered: {Key}", key);
        }
        else
        {
            _logger.LogWarning("Stream not found for unregistration: {Key}", key);
        }

        return Task.CompletedTask;
    }

    public Task UnregisterAllStreamsAsync()
    {
        var count = _registeredStreams.Count;
        _registeredStreams.Clear();
        _logger.LogInformation("All streams unregistered ({Count} total)", count);
        return Task.CompletedTask;
    }

    public ICollection<StreamRequest> GetRegisteredStreams()
    {
        return [.. _registeredStreams.Values];
    }

    #endregion

    #region IObserver Implementations

    void IObserver<MotionPacketEntity>.OnNext(MotionPacketEntity packet)
        => ProcessPacketAsync(packet).GetAwaiter().GetResult();

    void IObserver<MotionPacketEntity>.OnError(Exception error)
        => _logger.LogError(error, "Error in Motion packet stream");

    void IObserver<MotionPacketEntity>.OnCompleted()
        => _logger.LogInformation("Motion packet stream completed");

    void IObserver<SafetyPacketEntity>.OnNext(SafetyPacketEntity packet)
        => ProcessPacketAsync(packet).GetAwaiter().GetResult();

    void IObserver<SafetyPacketEntity>.OnError(Exception error)
        => _logger.LogError(error, "Error in Safety packet stream");

    void IObserver<SafetyPacketEntity>.OnCompleted()
        => _logger.LogInformation("Safety packet stream completed");

    void IObserver<OnVIFPacketEntity>.OnNext(OnVIFPacketEntity packet)
        => ProcessPacketAsync(packet).GetAwaiter().GetResult();

    void IObserver<OnVIFPacketEntity>.OnError(Exception error)
        => _logger.LogError(error, "Error in OnVIF packet stream");

    void IObserver<OnVIFPacketEntity>.OnCompleted()
        => _logger.LogInformation("OnVIF packet stream completed");

    #endregion
}
