using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs.Stream;
using PacketProcessing.Entities;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories.InfluxRepository;
using PacketProcessing.Services.Transmission;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Services.Playback;

/// <summary>
/// Service for managing playback of historical data streams from the database
/// Fetches packets and sends them to TransmissionService for delivery to clients
/// </summary>
public class PlaybackService : IPlaybackService
{
    #region Fields

    private readonly ILogger<PlaybackService> _logger;
    private readonly ITransmissionService _transmissionService;
    private readonly IInfluxRepositoryFactory _repoFactory;
    private readonly ConcurrentDictionary<string, PlaybackState> _activePlaybacks = new();

    #endregion

    #region Constructor

    public PlaybackService(
        ILogger<PlaybackService> logger, 
        ITransmissionService transmissionService,
        IInfluxRepositoryFactory repoFactory)
    {
        _logger = logger;
        _transmissionService = transmissionService;
        _repoFactory = repoFactory;
        
        _logger.LogInformation("PlaybackService initialized");
    }

    #endregion

    #region IPlaybackService Implementation

    public async Task StartPlaybackAsync(StreamRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        if (!request.IsPlayback)
        {
            _logger.LogWarning("Cannot start playback for non-playback StreamRequest");
            return;
        }

        var key = request.SubscriptionKey;

        if (_activePlaybacks.ContainsKey(key))
        {
            _logger.LogWarning("Playback already active for key: {Key}", key);
            return;
        }

        try
        {
            // Register stream in transmission service
            await _transmissionService.RegisterStreamAsync(request);
            
            // Start playback task
            var cts = new CancellationTokenSource();
            var task = request.DataPipe switch
            {
                DataPipes.Motion => PlaybackDataAsync<MotionPacketEntity>(request, cts.Token),
                DataPipes.Onvif => PlaybackDataAsync<OnVIFPacketEntity>(request, cts.Token),
                DataPipes.Safety => PlaybackDataAsync<SafetyPacketEntity>(request, cts.Token),
                _ => throw new ArgumentException($"Unsupported DataPipe: {request.DataPipe}")
            };

            var state = new PlaybackState(request, cts, task);
            _activePlaybacks.TryAdd(key, state);
            
            _logger.LogInformation(
                "Started playback: {DataPipe}.{Method} [{Start} to {End}]",
                request.DataPipe, request.MethodName, request.StartTimestamp, request.EndTimestamp);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error starting playback for key: {Key}", key);
            throw;
        }
    }

    public async Task StopPlaybackAsync(StreamRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        var key = request.SubscriptionKey;

        if (!_activePlaybacks.TryRemove(key, out var state))
        {
            _logger.LogWarning("No active playback found for key: {Key}", key);
            return;
        }

        try
        {
            await state.Cts.CancelAsync();
            
            try { await state.Task; }
            catch (OperationCanceledException) { }
            catch (Exception ex) { _logger.LogError(ex, "Error waiting for playback task"); }
            
            state.Cts.Dispose();
            
            await _transmissionService.UnregisterStreamAsync(request);
            
            _logger.LogInformation("Stopped playback: {Key}", key);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error stopping playback for key: {Key}", key);
            throw;
        }
    }

    public async Task StopAllPlaybacksAsync()
    {
        _logger.LogInformation("Stopping all playbacks ({Count} active)", _activePlaybacks.Count);

        var requests = _activePlaybacks.Values.Select(s => s.Request).ToList();
        
        foreach (var request in requests)
        {
            await StopPlaybackAsync(request);
        }

        _logger.LogInformation("All playbacks stopped");
    }

    public ICollection<StreamRequest> GetActivePlaybacks()
    {
        return [.. _activePlaybacks.Values.Select(s => s.Request)];
    }

    #endregion

    #region Private Helpers

    private async Task PlaybackDataAsync<T>(StreamRequest request, CancellationToken ct) where T : BasePacketEntity
    {
        var repo = _repoFactory.Get<T>();
        
        if (!request.StartTimestamp.HasValue || !request.EndTimestamp.HasValue)
        {
            _logger.LogWarning("Playback request missing timestamps");
            return;
        }
        
        var current = request.StartTimestamp.Value;
        var endTimestamp = request.EndTimestamp.Value;
        
        _logger.LogInformation(
            "Starting playback fetch: {DataPipe}.{Method} [{Start} to {End}]",
            request.DataPipe, request.MethodName, current, endTimestamp);

        try
        {
            while (!ct.IsCancellationRequested && current < endTimestamp)
            {
                var next = current.AddMilliseconds(request.IntervalMs);
                if (next > endTimestamp) next = endTimestamp;

                // Fetch packets from database
                var packets = await repo.GetPaginatedFromQuestDbAsyncWithInterval(
                    current, next, request.IntervalMs, OrderBy.Asc, 1, 1000);

                // Send each packet to TransmissionService
                foreach (var packet in packets)
                {
                    if (ct.IsCancellationRequested) break;
                    
                    // Send to appropriate observer method based on type
                    SendPacketToTransmission(packet);
                }

                _logger.LogDebug(
                    "Fetched and sent {Count} packets [{DataPipe}.{Method}]",
                    packets.Count(), request.DataPipe, request.MethodName);

                current = next;
                if (current < endTimestamp && !ct.IsCancellationRequested)
                    await Task.Delay(request.IntervalMs, ct);
            }
            
            _logger.LogInformation(
                "Playback fetch completed: {DataPipe}.{Method}",
                request.DataPipe, request.MethodName);
        }
        catch (OperationCanceledException)
        {
            _logger.LogInformation(
                "Playback fetch cancelled: {DataPipe}.{Method}",
                request.DataPipe, request.MethodName);
            throw;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex,
                "Playback fetch error: {DataPipe}.{Method}",
                request.DataPipe, request.MethodName);
            throw;
        }
    }

    private void SendPacketToTransmission<T>(T packet) where T : BasePacketEntity
    {
        switch (packet)
        {
            case MotionPacketEntity motion:
                ((IObserver<MotionPacketEntity>)_transmissionService).OnNext(motion);
                break;
            case SafetyPacketEntity safety:
                ((IObserver<SafetyPacketEntity>)_transmissionService).OnNext(safety);
                break;
            case OnVIFPacketEntity onvif:
                ((IObserver<OnVIFPacketEntity>)_transmissionService).OnNext(onvif);
                break;
            default:
                _logger.LogWarning("Unknown packet type: {Type}", packet.GetType().Name);
                break;
        }
    }

    #endregion
}

/// <summary>
/// State of an active playback stream
/// </summary>
internal sealed record PlaybackState(
    StreamRequest Request,
    CancellationTokenSource Cts,
    Task Task
);
