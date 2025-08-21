using System.ComponentModel.DataAnnotations;

namespace PacketProcessing.Entities;

public class OnVIFPacketEntity
{
    [Key]
    public Guid Id { get; set; } = Guid.NewGuid();
    public required bool Type { get; set; }
    public required string Description { get; set; }
    public float? Zoom { get; set; }
    public required float Measurement { get; set; }
    public required ulong Timestamp { get; set; }
}