// using Microsoft.Extensions.Logging;
// using PacketProcessing.DTOs.Data;
// using PacketProcessing.DTOs.Playback;
// using PacketProcessing.Entities;
// using PacketProcessing.Entities.Packet;
// using PacketProcessing.Hubs;
// using PacketProcessing.Playback;
// using PacketProcessing.Repositories.InfluxRepository;
// using PacketProcessing.Utils.Enums;

// namespace PacketProcessing.Services.Playback;

// public sealed class PlaybackService : IDisposable
// {
//     private readonly ILogger<PlaybackService> _logger;
//     private readonly IInfluxRepository<MotionPacketEntity> _motionRepository;
//     private readonly IInfluxRepository<OnVIFPacketEntity> _onvifRepository;
//     private readonly IInfluxRepository<SafetyPacketEntity> _safetyRepository;
//     private readonly HubClient _hubClient;

//     private readonly Dictionary<string, IDisposable> _activePlaybacks;
//     private bool _disposed = false;

//     public PlaybackService(
//         ILogger<PlaybackService> logger,
//         IInfluxRepository<MotionPacketEntity> motionRepository,
//         IInfluxRepository<OnVIFPacketEntity> onvifRepository,
//         IInfluxRepository<SafetyPacketEntity> safetyRepository,
//         HubClient hubClient)
//     {
//         _logger = logger ?? throw new ArgumentNullException(nameof(logger));
//         _motionRepository = motionRepository ?? throw new ArgumentNullException(nameof(motionRepository));
//         _onvifRepository = onvifRepository ?? throw new ArgumentNullException(nameof(onvifRepository));
//         _safetyRepository = safetyRepository ?? throw new ArgumentNullException(nameof(safetyRepository));
//         _hubClient = hubClient ?? throw new ArgumentNullException(nameof(hubClient));

//         _activePlaybacks = [];
//     }

//     public async Task StartPlaybackAsync(PlaybackDto playbackDto)
//     {
//         if (_disposed)
//         {
//             throw new ObjectDisposedException(nameof(PlaybackService));
//         }

//         _logger.LogInformation("Starting playback for {Count} packet entity types", playbackDto.DataPipes.Count);

//         var tasks = new List<Task>();

//         foreach (var dataPipe in playbackDto.DataPipes)
//         {
//             var entityTypeName = dataPipe.Key;
//             var filters = dataPipe.Value;

//             // Check if playback is already running for this entity type
//             if (_activePlaybacks.ContainsKey(entityTypeName))
//             {
//                 _logger.LogWarning("Playback is already running for entity type: {EntityType}", entityTypeName);
//                 continue;
//             }

//             try
//             {
//                 var playback = CreatePlaybackForEntityType(entityTypeName, filters);
//                 if (playback != null)
//                 {
//                     _activePlaybacks[entityTypeName] = playback;
//                     tasks.Add(StartPlaybackForEntityType(playback, entityTypeName));
//                     _logger.LogInformation("Started playback for entity type: {EntityType}", entityTypeName);
//                 }
//             }
//             catch (Exception ex)
//             {
//                 _logger.LogError(ex, "Failed to start playback for entity type: {EntityType}", entityTypeName);
//             }
//         }

//         await Task.WhenAll(tasks);
//         _logger.LogInformation("All playbacks started successfully");
//     }

//     public async Task StopPlaybackAsync()
//     {
//         if (_disposed) return;

//         _logger.LogInformation("Stopping {Count} active playbacks", _activePlaybacks.Count);

//         var stopTasks = new List<Task>();

//         foreach (var playback in _activePlaybacks.Values)
//         {
//             if (playback is IAsyncDisposable asyncDisposable)
//             {
//                 stopTasks.Add(asyncDisposable.DisposeAsync().AsTask());
//             }
//             else
//             {
//                 playback.Dispose();
//             }
//         }

//         await Task.WhenAll(stopTasks);
//         _activePlaybacks.Clear();

//         _logger.LogInformation("All playbacks stopped successfully");
//     }

//     public int ActivePlaybackCount => _activePlaybacks.Count;

//     public bool IsPlaybackActive(string entityTypeName)
//     {
//         return _activePlaybacks.ContainsKey(entityTypeName);
//     }

//     public IEnumerable<string> ActivePlaybackNames => _activePlaybacks.Keys;

//     private IDisposable? CreatePlaybackForEntityType(string entityTypeName, Dictionary<string, object> filters)
//     {
//         return entityTypeName switch
//         {
//             nameof(MotionPacketEntity) => new Playback<MotionPacketEntity>(
//                 new Logger<Playback<MotionPacketEntity>>(new LoggerFactory()),
//                 _hubClient.TransmitDataAsync,
//                 _motionRepository.GetPaginatedFromQuestDbAsyncWithInterval,
//                 filters),

//             nameof(OnVIFPacketEntity) => new Playback<OnVIFPacketEntity>(
//                 new Logger<Playback<OnVIFPacketEntity>>(new LoggerFactory()),
//                 _hubClient.TransmitDataAsync,
//                 _onvifRepository.GetPaginatedFromQuestDbAsyncWithInterval,
//                 filters),

//             nameof(SafetyPacketEntity) => new Playback<SafetyPacketEntity>(
//                 new Logger<Playback<SafetyPacketEntity>>(new LoggerFactory()),
//                 _hubClient.TransmitDataAsync,
//                 _safetyRepository.GetPaginatedFromQuestDbAsyncWithInterval,
//                 filters),

//             _ => throw new ArgumentException($"Unsupported entity type: {entityTypeName}", nameof(entityTypeName))
//         };
//     }

//     private async Task StartPlaybackForEntityType(IDisposable playback, string entityTypeName)
//     {
//         try
//         {
//             // Use reflection to call StartPlaybackAsync on the generic Playback<T> instance
//             var startMethod = playback.GetType().GetMethod("StartPlaybackAsync");
//             if (startMethod != null)
//             {
//                 var task = (Task)startMethod.Invoke(playback, null)!;
//                 await task;
//             }
//         }
//         catch (Exception ex)
//         {
//             _logger.LogError(ex, "Failed to start playback for entity type: {EntityType}", entityTypeName);
//             throw;
//         }
//     }

//     public void Dispose()
//     {
//         if (_disposed) return;

//         try
//         {
//             _logger.LogInformation("Disposing PlaybackService with {Count} active playbacks", _activePlaybacks.Count);

//             // Stop all playbacks first
//             foreach (var playback in _activePlaybacks.Values)
//             {
//                 try
//                 {
//                     playback.Dispose();
//                 }
//                 catch (Exception ex)
//                 {
//                     _logger.LogError(ex, "Error disposing playback");
//                 }
//             }

//             _activePlaybacks.Clear();
//         }
//         catch (Exception ex)
//         {
//             _logger.LogError(ex, "Error during PlaybackService disposal");
//         }
//         finally
//         {
//             _disposed = true;
//         }
//     }
// }
