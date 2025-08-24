using InfluxDB.Client.Core;
using QuestDB.Senders;

namespace PacketProcessing.Entities;

[Measurement("onvif_packets")]
public class OnVIFPacketEntity : BasePacketEntity
{
    [Column("type")]
    public required bool Type { get; set; }
    
    [Column("description")]
    public required string Description { get; set; }
    
    [Column("zoom")]
    public float? Zoom { get; set; }
    
    [Column("measurement")]
    public required float Measurement { get; set; }

    protected override string MeasurementName => "onvif_packets";
    
    protected override void WriteColumns(ISender sender)
    {
        sender.Column("type", Type);
        sender.Column("description", Description);
        if (Zoom.HasValue)
            sender.Column("zoom", Zoom.Value);
        sender.Column("measurement", Measurement);
    }
}