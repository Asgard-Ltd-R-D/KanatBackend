using PacketProcessing.DTOs;

namespace PacketProcessing.Telemetry;

/// <summary>
/// Service interface for telemetry data collection and snapshot generation
/// </summary>
public interface ITelemetryService
{
    /// <summary>
    /// Gets a snapshot of current telemetry data
    /// </summary>
    /// <returns>Current telemetry data snapshot</returns>
    Task<TelemetryDto> SnapshotAsync();
    
    /// <summary>
    /// Increments the captured counter
    /// </summary>
    /// <param name="count">Number to increment by (default 1)</param>
    void IncrementCaptured(long count = 1);
    
    /// <summary>
    /// Increments the parsed counter
    /// </summary>
    /// <param name="count">Number to increment by (default 1)</param>
    void IncrementParsed(long count = 1);
    
    /// <summary>
    /// Increments the dropped counter
    /// </summary>
    /// <param name="count">Number to increment by (default 1)</param>
    void IncrementDropped(long count = 1);
    
    /// <summary>
    /// Increments the flushed counter
    /// </summary>
    /// <param name="count">Number to increment by (default 1)</param>
    void IncrementFlushed(long count = 1);
    
    /// <summary>
    /// Increments the failed counter
    /// </summary>
    /// <param name="count">Number to increment by (default 1)</param>
    void IncrementFailed(long count = 1);
    
    /// <summary>
    /// Increments the backpressure counter
    /// </summary>
    /// <param name="count">Number to increment by (default 1)</param>
    void IncrementBackpressure(long count = 1);
    
    /// <summary>
    /// Updates the average latency
    /// </summary>
    /// <param name="latency">New latency value</param>
    void UpdateLatency(double latency);
    
    /// <summary>
    /// Increments motion captured counter
    /// </summary>
    /// <param name="count">Number to increment by (default 1)</param>
    void IncrementMotionCaptured(long count = 1);
    
    /// <summary>
    /// Increments safety captured counter
    /// </summary>
    /// <param name="count">Number to increment by (default 1)</param>
    void IncrementSafetyCaptured(long count = 1);
    
    /// <summary>
    /// Increments OnVIF captured counter
    /// </summary>
    /// <param name="count">Number to increment by (default 1)</param>
    void IncrementOnvifCaptured(long count = 1);
    
    /// <summary>
    /// Updates channel statistics for a specific channel
    /// </summary>
    /// <param name="channelName">Name of the channel</param>
    /// <param name="capacity">Channel capacity</param>
    /// <param name="currentSize">Current channel size</param>
    /// <param name="utilizationPercent">Channel utilization percentage</param>
    void UpdateChannelStats(string channelName, int capacity, int currentSize, double utilizationPercent);
    
    /// <summary>
    /// Resets all telemetry counters
    /// </summary>
    void Reset();
    
    /// <summary>
    /// Checks if there are any changes since the last snapshot
    /// </summary>
    /// <returns>True if there are changes, false otherwise</returns>
    bool HasChanges();
    
    /// <summary>
    /// Marks that a snapshot has been taken (clears the changes flag)
    /// </summary>
    void MarkSnapshotTaken();
    
    /// <summary>
    /// Sets test data for demonstration purposes
    /// </summary>
    void SetTestData();
}
