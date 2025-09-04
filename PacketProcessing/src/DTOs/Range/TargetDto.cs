namespace PacketProcessing.DTOs.Range;

/// <summary>
/// Data Transfer Object for TargetEntity
/// </summary>
public class TargetDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public int PosX { get; set; }
    public int PosY { get; set; }
    public int CenterX { get; set; }
    public int CenterY { get; set; }
}
