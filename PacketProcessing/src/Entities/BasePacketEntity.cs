using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using QuestDB.Senders;
using static PacketProcessing.Context.QuestDbContext;

namespace PacketProcessing.Entities;

public abstract class BasePacketEntity : BaseEntity
{
    /// <summary>
    /// Is command or report
    /// </summary>
    [Column("isCmd")]
    public required bool IsCmd { get; set; } = true;

    /// <summary>
    /// Method name
    /// </summary>
    [Column("description")]
    [StringLength(128)]
    public required string Description { get; set; }

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
    /// Build the subscription key for the stream request, this is used to identify the stream request and to filter the packets.
    /// For none motion packets, the axis is not included in the subscription key, and the key will set as follows: {DataPipe}|{Description}|{IsCmd}
    /// For motion packets, the axis is included in the subscription key, and the key will set as follows: {DataPipe}|{Description}|{IsCmd}|{Axis}
    /// 
    /// Note: The subscription key is lowercased before returning.
    /// </summary>
    /// <returns>The subscription key</returns>
    public abstract string GetSubscriptionKey();
}