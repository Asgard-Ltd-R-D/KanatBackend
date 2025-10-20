using PacketProcessing.Services.Playback;
using PacketProcessing.Services.Realtime;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Services;

/// <summary>
/// State manager that provides access to real-time and playback services
/// and manages application state
/// </summary>
public interface IStateManager
{
    /// <summary>
    /// Get the real-time service
    /// </summary>
    IRealtimeService Realtime { get; }
    
    /// <summary>
    /// Get the playback service
    /// </summary>
    IPlaybackService Playback { get; }
    
    /// <summary>
    /// Get current application state
    /// </summary>
    States CurrentState { get; }
    
    /// <summary>
    /// Set application state
    /// </summary>
    void SetState(States state);
}
