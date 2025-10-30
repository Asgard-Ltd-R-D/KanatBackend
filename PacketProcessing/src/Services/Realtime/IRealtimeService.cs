using PacketProcessing.DTOs;
using PacketProcessing.DTOs.Range;
using PacketProcessing.DTOs.Conf;
using PacketProcessing.Utils.Enums;
using static PacketProcessing.DTOs.Range.RangeDto;

namespace PacketProcessing.Services.Realtime;

/// <summary>
/// Real-time service for managing packet capture pipeline
/// Orchestrates handlers and writers for all data pipes
/// </summary>
public interface IRealtimeService
{
    /// <summary>
    /// Start the realtime service with a configuration
    /// </summary>
    /// <param name="cancellationToken"></param>
    /// <param name="config"></param>
    /// <returns></returns>
    Task StartAsync(CancellationToken cancellationToken, BPFConfDto config);

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
    /// Get the current range
    /// </summary>
    /// <returns>The current range</returns>
    Task<RangeDto?> GetCurrentRangeAsync();

    /// <summary>
    /// Set the current range
    /// </summary>
    /// <param name="range">The range to set</param>
    Task SetCurrentRangeAsync(RangeDto range);

    /// <summary>
    /// Reset all statistics counters to zero
    /// </summary>
    void ResetStats();

    /// <summary>
    /// Get current statistics aggregated from all handlers and writers
    /// </summary>
    TelemetryDto GetStats();

    /// <summary>
    /// Get available network device names from the underlying device service
    /// </summary>
    ICollection<string> GetAvailableDeviceNames();

    /// <summary>
    /// Check if the realtime service is active
    /// </summary>
    /// <returns>True if active, false otherwise</returns>
    bool IsActive { get; }
}

