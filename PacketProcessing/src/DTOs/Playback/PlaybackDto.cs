namespace PacketProcessing.DTOs.Playback;

/// <summary>
/// DTO for configuring playback operations for packet entities
/// </summary>
public class PlaybackDto
{
    /// <summary>
    /// Dictionary mapping packet entity names to their respective filters
    /// Key: Name of the packet entity type (e.g., "MotionPacketEntity", "OnVIFPacketEntity", "SafetyPacketEntity")
    /// Value: Dictionary of filters to apply to that entity type
    /// </summary>
    public required Dictionary<string, Dictionary<string, object>> DataPipes { get; set; }
}
