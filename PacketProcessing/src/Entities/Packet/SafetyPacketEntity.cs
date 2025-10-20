using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using QuestDB.Senders;

namespace PacketProcessing.Entities.Packet;

[Table("safety_packets")]
public class SafetyPacketEntity : BasePacketEntity
{
    [Column("name")]
    public required string Name { get; set; }
    
    [Column("opCode")]
    [StringLength(32)]
    public required string OpCode { get; set; }
    
    [Column("state")]
    [StringLength(64)]
    public required string State { get; set; }

    public override string TableName => "safety_packets";
    
    public override void WriteColumns(ISender sender)
    {
        sender.Column("isCmd", IsCmd);
        sender.Column("name", Name);
        sender.Column("opCode", OpCode);
        sender.Column("description", Description);
        sender.Column("state", State);
    }
}
