using InfluxDB.Client.Core;
using QuestDB.Senders;

namespace PacketProcessing.Entities;

[Measurement("safety_packets")]
public class SafetyPacketEntity : BasePacketEntity
{
    [Column("type")]
    public required bool Type { get; set; }
    
    [Column("opCode")]
    public required string OpCode { get; set; }
    
    [Column("opCodeDescription")]
    public required string OpCodeDescription { get; set; }
    
    [Column("state")]
    public required string State { get; set; }

    protected override string MeasurementName => "safety_packets";
    
    protected override void WriteColumns(ISender sender)
    {
        sender.Column("type", Type);
        sender.Column("opCode", OpCode);
        sender.Column("opCodeDescription", OpCodeDescription);
        sender.Column("state", State);
    }
    
    public override IReadOnlyList<(string Name, string Type, bool IsSymbol, bool Indexed)> GetQuestColumns()
    {
        var baseCols = base.GetQuestColumns(); // id, timestamp
        return new List<(string, string, bool, bool)>(baseCols)
        {
            ("type",               "BOOLEAN", false, false),
            ("opCode",             "STRING",  false, true),
            ("opCodeDescription",  "STRING",  false, false),
            ("state",              "STRING",  false, true)
        };
    }
}