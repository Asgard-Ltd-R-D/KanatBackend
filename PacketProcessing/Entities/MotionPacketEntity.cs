using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using QuestDB.Senders;

namespace PacketProcessing.Entities;

[Table("motion_packets")]
public class MotionPacketEntity : BasePacketEntity
{
    [Column("type")]
    public required bool Type { get; set; }
    
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
        sender.Column("type", Type);
        sender.Column("opCode", OpCode);
        sender.Column("opCodeDescription", OpCodeDescription);
        sender.Column("axis", Axis);
        if (FloatValue.HasValue)
            sender.Column("floatValue", FloatValue.Value);
        else
            sender.NullableColumn("floatValue", float.NaN);
    }
}