using Microsoft.Extensions.Logging;
using PacketProcessing.Services.Playback;
using PacketProcessing.Services.Realtime;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Services;

/// <summary>
/// State manager that provides access to real-time and playback services
/// and manages application state centrally
/// </summary>
public class StateManager : IStateManager
{
    private readonly ILogger<StateManager> _logger;
    private States _currentState = States.Realtime;
    private readonly object _stateLock = new();

    public StateManager(
        ILogger<StateManager> logger,
        IRealtimeService realtimeService,
        IPlaybackService playbackService)
    {
        _logger = logger;
        Realtime = realtimeService;
        Playback = playbackService;
        
        _logger.LogInformation("StateManager initialized with state: {State}", _currentState);
    }

    public IRealtimeService Realtime { get; }
    
    public IPlaybackService Playback { get; }

    public States CurrentState
    {
        get
        {
            lock (_stateLock)
            {
                return _currentState;
            }
        }
    }

    public void SetState(States state)
    {
        lock (_stateLock)
        {
            var previousState = _currentState;
            
            if (previousState != state)
            {
                _currentState = state;
                _logger.LogInformation(
                    "Application state changed: {PreviousState} → {NewState}",
                    previousState, state);
            }
        }
    }
}
