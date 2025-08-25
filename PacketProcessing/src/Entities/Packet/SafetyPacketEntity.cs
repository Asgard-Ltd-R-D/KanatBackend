using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using QuestDB.Senders;

namespace PacketProcessing.Entities.Packet;

[Table("safety_packets")]
public class SafetyPacketEntity : BasePacketEntity
{
    [Column("type")]
    public required bool Type { get; set; }
    
    [Column("opCode")]
    [StringLength(32)]
    public required string OpCode { get; set; }
    
    [Column("opCodeDescription")]
    [StringLength(128)]
    public required string OpCodeDescription { get; set; }
    
    [Column("state")]
    [StringLength(64)]
    public required string State { get; set; }

    public override string TableName => "safety_packets";
    
    public override void WriteColumns(ISender sender)
    {
        sender.Column("type", Type);
        sender.Column("opCode", OpCode);
        sender.Column("opCodeDescription", OpCodeDescription);
        sender.Column("state", State);
    }
}
