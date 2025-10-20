namespace PacketProcessing.DTOs.Packet;

/// <summary>
/// Data Transfer Object for SafetyPacketEntity
/// </summary>
public class SafetyPacketDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public string Name { get; set; } = string.Empty;
    public bool IsCmd { get; set; } = true;
    public string OpCode { get; set; } = string.Empty;
    public string Description { get; set; } = string.Empty;
    public string State { get; set; } = string.Empty;
}
