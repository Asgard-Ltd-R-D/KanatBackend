using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using PacketProcessing.Entities;

namespace PacketProcessing.Entities.Range;

/// <summary>
/// Represents a range in the range system
/// </summary>
[Table("ranges")]
public class RangeEntity : BaseEntity
{
    [Column("start_time")]
    public required long StartTime { get; set; }
    
    [Column("end_time")]
    public required long EndTime { get; set; }
    
    [Column("description")]
    [MaxLength(500)]
    public required string Description { get; set; }


    // Navigation properties
    public virtual ICollection<EventEntity> Events { get; set; } = [];
}
