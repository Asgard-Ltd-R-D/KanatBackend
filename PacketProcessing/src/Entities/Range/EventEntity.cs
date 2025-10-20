using System.ComponentModel.DataAnnotations.Schema;

namespace PacketProcessing.Entities.Range;

/// <summary>
/// Represents an event in the range system
/// </summary>
[Table("events")]
public class EventEntity : BaseEntity
{
    [Column("start_time")]
    public required long Start { get; set; }
    
    [Column("end_time")]
    public required long End { get; set; }

    [Column("range_id")]
    public Guid RangeId { get; set; }

    // Navigation properties
    public virtual ICollection<HitEntity> Hits { get; set; } = [];

    [ForeignKey("RangeId")]
    public virtual RangeEntity Range { get; set; } = null!;
}
