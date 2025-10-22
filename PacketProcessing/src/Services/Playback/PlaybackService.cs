using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs.Stream;
using PacketProcessing.Entities;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories.InfluxRepository;
using PacketProcessing.Services.Transmission;
using PacketProcessing.Utils.Enums;
using PacketProcessing.Utils.Observers;

namespace PacketProcessing.Services.Playback;

/// <summary>
/// Service for managing playback of historical data streams from the database
/// Fetches packets and sends them to TransmissionService for delivery to clients
/// </summary>
public class PlaybackService : IPlaybackService, IObservable<BasePacketEntity>
{
    #region Fields

    private readonly ILogger<PlaybackService> _logger;
    private readonly ITransmissionService? _transmissionService;
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

    /// <summary>
    /// Starts playback for a stream request
    /// Note: StreamRequest should be registered to TransmissionService BEFORE calling this method
    /// This method only fetches packets and sends them to TransmissionService.OnNext()
    /// </summary>
    public Task StartPlaybackAsync(StreamRequestDto request)
    {
        ArgumentNullException.ThrowIfNull(request);

        var key = request.SubscriptionKey;

        if (_activePlaybacks.ContainsKey(key))
        {
            _logger.LogWarning("Playback already active for key: {Key}", key);
            return Task.CompletedTask;
        }

        // Validate playback request has required fields
        // if (!request.StartTimestamp.HasValue || !request.EndTimestamp.HasValue)
        // {
        //     throw new ArgumentException("Playback request must have StartTimestamp and EndTimestamp");
        // }

        // Start playback task - fetches packets and sends them to TransmissionService
        var cts = new CancellationTokenSource();
        var task = request.DataPipe switch
        {
            DataPipes.Motion => PlaybackDataAsync<MotionPacketEntity>(request, cts.Token),
            DataPipes.OnVIF => PlaybackDataAsync<OnVIFPacketEntity>(request, cts.Token),
            DataPipes.Safety => PlaybackDataAsync<SafetyPacketEntity>(request, cts.Token),
            _ => throw new ArgumentException($"Unsupported DataPipe: {request.DataPipe}")
        };

        var state = new PlaybackState(request, cts, task);
        _activePlaybacks.TryAdd(key, state);
        
        // _logger.LogInformation(
        //     "Playback started: {DataPipe}.{Method} [{Start} to {End}]",
        //     request.DataPipe, request.Description, request.StartTimestamp, request.EndTimestamp);

        return Task.CompletedTask;
    }

    public async Task StopPlaybackAsync(StreamRequestDto request)
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

    public ICollection<StreamRequestDto> GetActivePlaybacks()
    {
        return [.. _activePlaybacks.Values.Select(s => s.Request)];
    }

    #endregion

    #region Private Helpers

    private async Task PlaybackDataAsync<T>(StreamRequestDto request, CancellationToken ct) where T : BasePacketEntity
    {
        await Task.CompletedTask;
        // var repo = _repoFactory.Get<T>();
        // var current = request.StartTimestamp!.Value;
        // var endTimestamp = request.EndTimestamp!.Value;
        
        // _logger.LogInformation(
        //     "Starting playback fetch: {DataPipe}.{Method} [{Start} to {End}]",
        //     request.DataPipe, request.Description, current, endTimestamp);

        // try
        // {
        //     while (!ct.IsCancellationRequested && current < endTimestamp)
        //     {
        //         var next = current.AddMilliseconds(request.IntervalMs);
        //         if (next > endTimestamp) next = endTimestamp;

        //         // Fetch packets from database
        //         var packets = await repo.GetPaginatedFromQuestDbAsyncWithInterval(
        //             current, next, request.IntervalMs, OrderBy.Asc, 1, 1000);

        //         // Send each packet to TransmissionService
        //         foreach (var packet in packets)
        //         {
        //             if (ct.IsCancellationRequested) break;
                    
        //             // Send to appropriate observer method based on type
        //             _transmissionService?.OnNext(packet);
        //         }

        //         _logger.LogDebug(
        //             "Fetched and sent {Count} packets [{DataPipe}.{Method}]",
        //             packets.Count(), request.DataPipe, request.Description);

        //         current = next;
        //         if (current < endTimestamp && !ct.IsCancellationRequested)
        //             await Task.Delay(request.IntervalMs, ct);
        //     }
            
        //     _logger.LogInformation(
        //         "Playback fetch completed: {DataPipe}.{Method}",
        //         request.DataPipe, request.Description);
        // }
        // catch (OperationCanceledException)
        // {
        //     _logger.LogInformation(
        //         "Playback fetch cancelled: {DataPipe}.{Method}",
        //         request.DataPipe, request.Description);
        //     throw;
        // }
        // catch (Exception ex)
        // {
        //     _logger.LogError(ex,
        //         "Playback fetch error: {DataPipe}.{Method}",
        //         request.DataPipe, request.Description);
        //     throw;
        // }
    }

    public IDisposable Subscribe(IObserver<BasePacketEntity> observer)
    {
        ArgumentNullException.ThrowIfNull(observer);
        return new Unsubscriber<BasePacketEntity>([observer], observer);
    }

    #endregion
}

/// <summary>
/// State of an active playback stream
/// </summary>
internal sealed record PlaybackState(
    StreamRequestDto Request,
    CancellationTokenSource Cts,
    Task Task
);
