using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using PacketProcessing.Entities;

namespace PacketProcessing.Entities.Range;

/// <summary>
/// Represents a target in the range system
/// </summary>
[Table("targets")]
public class TargetEntity : BaseEntity
{
    [Column("pos_x")]
    public required int PosX { get; set; }
    
    [Column("pos_y")]
    public required int PosY { get; set; }
    
    [Column("center_x")]
    public required int CenterX { get; set; }
    
    [Column("center_y")]
    public required int CenterY { get; set; }

    // Navigation properties
    public virtual ICollection<HitEntity> Hits { get; set; } = [];
}
