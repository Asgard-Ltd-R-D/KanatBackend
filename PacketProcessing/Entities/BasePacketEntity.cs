using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using PacketProcessing.Utils.QuestDB;
using QuestDB.Senders;

namespace PacketProcessing.Entities;

public abstract class BasePacketEntity
{
    [Key]
    [Column("id")]
    public Guid Id { get; set; } = Guid.NewGuid();
    
    [Column("timestamp")]
    public required DateTime Timestamp { get; set; } = DateTime.UtcNow;
    
    /// <summary>
    /// Gets the table name for this entity
    /// </summary>
    public abstract string TableName { get; }
    
    /// <summary>
    /// Writes the columns to the sender for this entity
    /// </summary>
    /// <param name="sender">The sender to write columns to</param>
    public abstract void WriteColumns(ISender sender);
    
    /// <summary>
    /// Creates a RowMap function to write this object to the sender
    /// </summary>
    /// <returns>RowMap function to activate</returns>
    public virtual RowMap ToRowMap()
    {
        var table = TableName;
        var tsUtc = DateTime.SpecifyKind(Timestamp, DateTimeKind.Utc);

        return new RowMap(
            table,
            tsUtc,
            apply: sender =>
            {
                sender
                    .Symbol("id", Id.ToString("N"));

                WriteColumns(sender);

                sender.At(tsUtc);
            });
    }
}