using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace PacketProcessing.Entities;

/// <summary>
/// Abstract base class for all entities in the system
/// </summary>
public abstract class BaseEntity
{
    // This is a marker interface/base class for all entities
    [Key]
    [Column("id")]
    public Guid Id { get; set; } = Guid.NewGuid();
    
    [Column("timestamp")]
    public required DateTime Timestamp { get; set; } = DateTime.UtcNow;
}
