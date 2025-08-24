using InfluxDB.Client.Core;
using QuestDB.Senders;

namespace PacketProcessing.Entities;

[Measurement("motion_packets")]
public class MotionPacketEntity : BasePacketEntity
{
    [Column("type")]
    public required bool Type { get; set; }
    
    [Column("opCode")]
    public required string OpCode { get; set; }
    
    [Column("opCodeDescription")]
    public required string OpCodeDescription { get; set; }
    
    [Column("axis")]
    public required int Axis { get; set; }
    
    [Column("floatValue")]
    public float? FloatValue { get; set; }

    protected override string MeasurementName => "motion_packets";
    
    protected override void WriteColumns(ISender sender)
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
    
    public override IReadOnlyList<(string Name, string Type, bool IsSymbol, bool Indexed)> GetQuestColumns()
    {
        var baseCols = base.GetQuestColumns(); // id, timestamp
        return new List<(string, string, bool, bool)>(baseCols)
        {
            ("type", "BOOLEAN", false, false),
            ("opCode", "STRING", false, true),            
            ("opCodeDescription", "STRING", false, false),
            ("axis", "INT", false, false),
            ("floatValue", "DOUBLE", false, false)
        };
    }
}