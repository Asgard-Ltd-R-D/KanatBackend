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
    // Per-entity capture fail
    public long MotionCaptureFail { get; set; }
    public long SafetyCaptureFail { get; set; }
    public long OnvifCaptureFail { get; set; }
    // Per-entity parse
    public long MotionParseSuccess { get; set; }
    public long MotionParseFail { get; set; }
    public long SafetyParseSuccess { get; set; }
    public long SafetyParseFail { get; set; }
    public long OnvifParseSuccess { get; set; }
    public long OnvifParseFail { get; set; }
    // Per-entity flush
    public long MotionFlushSuccess { get; set; }
    public long MotionFlushFail { get; set; }
    public long SafetyFlushSuccess { get; set; }
    public long SafetyFlushFail { get; set; }
    public long OnvifFlushSuccess { get; set; }
    public long OnvifFlushFail { get; set; }
    
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
    public int Workers { get; set; }
    public double AvgLatencyMs { get; set; }
}

