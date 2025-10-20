namespace PacketProcessing.DTOs.Packet;

/// <summary>
/// Data Transfer Object for OnVIFPacketEntity
/// </summary>
public class OnVIFPacketDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public bool IsCmd { get; set; }
    public string Description { get; set; } = string.Empty;
    public double? Zoom { get; set; }
    public double? Measurement { get; set; }
}
