using System.ComponentModel.DataAnnotations.Schema;
using QuestDB.Senders;
using static PacketProcessing.Context.QuestDbContext;

namespace PacketProcessing.Entities;

public abstract class BasePacketEntity : BaseEntity
{
    [Column("isCmd")]
    public required bool IsCmd { get; set; } = true;

    /// <summary>
    /// Gets the table name for this entity
    /// </summary>
    public abstract string TableName { get; }
    
    /// <summary>
    /// Writes the columns to the sender for this entity
    /// </summary>
    /// <param name="sender">The sender to write columns to</param>
    public abstract void WriteColumns(ISender sender);
}