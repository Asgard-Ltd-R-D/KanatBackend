using PacketProcessing.DTOs;
using PacketProcessing.Utils.Constants;

namespace PacketProcessing.Services.Orchestration;

/// <summary>
/// Orchestrates the pipeline of handlers and writers.
/// Ensures handlers subscribe, writers run, and everything stops cleanly.
/// </summary>
public interface IPipelineOrchestrator
{
    /// <summary>
    /// Initialize and subscribe all handlers based on configuration.
    /// <param name="cancellationToken">Cancellation token</param>
    /// <param name="deviceName">Device name</param>
    /// </summary>
    Task StartAsync(CancellationToken cancellationToken, string deviceName);

    /// <summary>
    /// Unsubscribe and stop all handlers and writers.
    /// <param name="cancellationToken">Cancellation token</param>
    /// </summary>
    Task StopAsync(CancellationToken cancellationToken);

    /// <summary>
    /// Get statistics about the pipeline.
    /// </summary>
    TelemetryDto GetStats();
    
    /// <summary>
    /// Reset all statistics counters to zero.
    /// </summary>
    void ResetStats();
    
    /// <summary>
    /// Gets the current application state.
    /// </summary>
    States GetCurrentState();
    
    /// <summary>
    /// Sets the application state.
    /// </summary>
    void SetState(States state);
}
