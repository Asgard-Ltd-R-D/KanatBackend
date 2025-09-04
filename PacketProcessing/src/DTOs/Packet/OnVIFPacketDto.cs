namespace PacketProcessing.DTOs.Packet;

/// <summary>
/// Data Transfer Object for OnVIFPacketEntity
/// </summary>
public class OnVIFPacketDto
{
    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public bool Type { get; set; }
    public string Description { get; set; } = string.Empty;
    public float? Zoom { get; set; }
    public float Measurement { get; set; }
}
