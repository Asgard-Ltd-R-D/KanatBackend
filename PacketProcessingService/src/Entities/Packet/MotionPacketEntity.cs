using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using PacketProcessing.Utils.Constants;
using PacketProcessing.Utils.Enums;
using QuestDB.Senders;

namespace PacketProcessing.Entities.Packet;

[Table(Constants.MOTION_PACKETS_TAG)]
public class MotionPacketEntity : BasePacketEntity
{
    [Column("opCode")]
    [StringLength(32)]
    public required string OpCode { get; set; }

    [Column("axis")]
    public required int Axis { get; set; }
    
    [Column("value")]
    public double? Value { get; set; }

    public override string TableName => Constants.MOTION_PACKETS_TAG;
    
    public override void WriteColumns(ISender sender)
    {
        sender.Column("isCmd", IsCmd);
        sender.Column("opCode", OpCode);
        sender.Column("description", Description);
        sender.Column("axis", Axis);
        if (Value.HasValue) sender.Column("value", Value.Value);
        else sender.NullableColumn("value", double.NaN);
    }

    public override string GetSubscriptionKey()
    {
        return $"{DataPipes.Motion}|{Description}|{IsCmd}|{Axis}".ToLower();
    }
}
