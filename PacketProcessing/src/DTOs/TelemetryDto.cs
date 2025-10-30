namespace PacketProcessing.DTOs;

/// <summary>
/// DTO for telemetry data returned by the status endpoint
/// </summary>
public class TelemetryDto
{
    public long Captured { get; set; }
    public long Parsed { get; set; }
    public long Dropped { get; set; }
    public long Flushed { get; set; }
    public long Failed { get; set; }
    public long Backpressure { get; set; }
    public double AvgLatency { get; set; }
    public long MotionCaptured { get; set; }
    public long SafetyCaptured { get; set; }
    public long OnvifCaptured { get; set; }
    
    // Channel statistics (Raw: Capture -> Parse)
    public ChannelStatsDto? MotionRawChannel { get; set; }
    public ChannelStatsDto? SafetyRawChannel { get; set; }
    public ChannelStatsDto? OnvifRawChannel { get; set; }
    
    // Channel statistics (Parsed: Parse -> DB)
    public ChannelStatsDto? MotionParsedChannel { get; set; }
    public ChannelStatsDto? SafetyParsedChannel { get; set; }
    public ChannelStatsDto? OnvifParsedChannel { get; set; }
}

/// <summary>
/// Channel statistics for monitoring queue state
/// </summary>
public class ChannelStatsDto
{
    public int Capacity { get; set; }
    public int CurrentSize { get; set; }
    public double UtilizationPercent { get; set; }
    public int WorkerCount { get; set; }
    public double AvgLatencyMs { get; set; }
}

