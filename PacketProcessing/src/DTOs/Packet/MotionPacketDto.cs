namespace PacketProcessing.DTOs.Packet;

/// <summary>
/// Data Transfer Object for MotionPacketEntity
/// </summary>
public class MotionPacketDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public bool Type { get; set; }
    public string OpCode { get; set; } = string.Empty;
    public string OpCodeDescription { get; set; } = string.Empty;
    public int Axis { get; set; }
    public float? FloatValue { get; set; }
}
