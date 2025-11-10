namespace PacketProcessing.DTOs.Range;

/// <summary>
/// Data Transfer Object for EventEntity
/// </summary>
public class EventDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public long Start { get; set; }
    public long End { get; set; }
    public Guid RangeId { get; set; }
}
