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
}