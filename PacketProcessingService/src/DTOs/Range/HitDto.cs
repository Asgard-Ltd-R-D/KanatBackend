namespace PacketProcessing.DTOs.Range;

/// <summary>
/// Data Transfer Object for HitEntity
/// </summary>
public class HitDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public float RangeToTarget { get; set; }
    public int PosX { get; set; }
    public int PosY { get; set; }
    public int CenterX { get; set; }
    public int CenterY { get; set; }
    public Guid TargetId { get; set; }
    public Guid EventId { get; set; }
}
