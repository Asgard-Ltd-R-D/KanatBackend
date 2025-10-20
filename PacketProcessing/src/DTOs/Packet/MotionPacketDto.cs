namespace PacketProcessing.DTOs.Packet;

/// <summary>
/// Data Transfer Object for MotionPacketEntity
/// </summary>
public class MotionPacketDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public bool IsCmd { get; set; }
    public string OpCode { get; set; } = string.Empty;
    public string Description { get; set; } = string.Empty;
    public int Axis { get; set; }
    public double? Value { get; set; }
}
