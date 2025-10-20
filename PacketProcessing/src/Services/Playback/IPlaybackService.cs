using PacketProcessing.DTOs.Stream;

namespace PacketProcessing.Services.Playback;

/// <summary>
/// Service for managing playback of historical data streams
/// </summary>
public interface IPlaybackService
{
    /// <summary>
    /// Starts playback stream for the given request
    /// </summary>
    /// <param name="request">The stream request configuration</param>
    Task StartPlaybackAsync(StreamRequest request);
    
    /// <summary>
    /// Stops playback stream for the given request
    /// </summary>
    /// <param name="request">The stream request to stop</param>
    Task StopPlaybackAsync(StreamRequest request);
    
    /// <summary>
    /// Stops all active playback streams
    /// </summary>
    Task StopAllPlaybacksAsync();
    
    /// <summary>
    /// Gets all active playback streams
    /// </summary>
    ICollection<StreamRequest> GetActivePlaybacks();
}
