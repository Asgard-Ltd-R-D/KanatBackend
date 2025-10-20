using PacketProcessing.DTOs;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Services.Realtime;

/// <summary>
/// Real-time service for managing packet capture pipeline
/// Orchestrates handlers and writers for all data pipes
/// </summary>
public interface IRealtimeService
{
    /// <summary>
    /// Initialize and subscribe all handlers based on configuration
    /// </summary>
    /// <param name="cancellationToken">Cancellation token</param>
    /// <param name="deviceName">Device name</param>
    Task StartAsync(CancellationToken cancellationToken, string deviceName);

    /// <summary>
    /// Unsubscribe and stop all handlers and writers
    /// </summary>
    /// <param name="cancellationToken">Cancellation token</param>
    Task StopAsync(CancellationToken cancellationToken);

    /// <summary>
    /// Get statistics about the pipeline
    /// </summary>
    TelemetryDto GetStats();
    
    /// <summary>
    /// Reset all statistics counters to zero
    /// </summary>
    void ResetStats();
}

