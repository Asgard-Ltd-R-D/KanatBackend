using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace PacketProcessing.Entities;

public class OnVIFPacketEntity
{
    [Key]
    public Guid Id { get; set; } = Guid.NewGuid();
    public bool Type { get; set; }
    public string Description { get; set; }
    public float? Zoom { get; set; }
    public float Measurement { get; set; }
    [DatabaseGenerated(DatabaseGeneratedOption.Identity)]
    public ulong Timestamp { get; set; }
}