using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using QuestDB.Senders;

namespace PacketProcessing.Entities.Packet;

[Table("motion_packets")]
public class MotionPacketEntity : BasePacketEntity
{
    [Column("isCmd")]
    public required bool IsCmd { get; set; }
    
    [Column("opCode")]
    [StringLength(32)]
    public required string OpCode { get; set; }
    
    [Column("opCodeDescription")]
    [StringLength(128)]
    public required string OpCodeDescription { get; set; }
    
    [Column("axis")]
    public required int Axis { get; set; }
    
    [Column("floatValue")]
    public float? FloatValue { get; set; }

    public override string TableName => "motion_packets";
    
    public override void WriteColumns(ISender sender)
    {
        sender.Column("isCmd", IsCmd);
        sender.Column("opCode", OpCode);
        sender.Column("opCodeDescription", OpCodeDescription);
        sender.Column("axis", Axis);
        if (FloatValue.HasValue) sender.Column("floatValue", FloatValue.Value);
        else sender.NullableColumn("floatValue", float.NaN);
    }
}
