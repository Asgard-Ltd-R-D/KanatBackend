using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using PacketProcessing.Entities;

namespace PacketProcessing.Entities.Range;

/// <summary>
/// Represents a hit in the range system
/// </summary>
[Table("hits")]
public class HitEntity : BaseEntity
{
    [Column("range_to_target")]
    public required float RangeToTarget { get; set; }
    
    [Column("pos_x")]
    public required int PosX { get; set; }
    
    [Column("pos_y")]
    public required int PosY { get; set; }
    
    [Column("center_x")]
    public required int CenterX { get; set; }
    
    [Column("center_y")]
    public required int CenterY { get; set; }

    // Foreign keys
    [Column("target_id")]
    public Guid TargetId { get; set; }
    
    [Column("event_id")]
    public Guid EventId { get; set; }

    // Navigation properties
    [ForeignKey("TargetId")]
    public virtual TargetEntity Target { get; set; } = null!;
    
    [ForeignKey("EventId")]
    public virtual EventEntity Event { get; set; } = null!;
}
