namespace PacketProcessing.DTOs.Range;

/// <summary>
/// Data Transfer Object for RangeEntity
/// </summary>
public class RangeDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public long Start { get; set; }
    public long End { get; set; }
    public string Description { get; set; } = string.Empty;
}
