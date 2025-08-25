using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using QuestDB.Senders;

namespace PacketProcessing.Entities;

[Table("onvif_packets")]
public class OnVIFPacketEntity : BasePacketEntity
{
    [Column("type")]
    public required bool Type { get; set; }
    
    [Column("description")]
    [StringLength(128)]
    public required string Description { get; set; }
    
    [Column("zoom")]
    public float? Zoom { get; set; }
    
    [Column("measurement")]
    public required float Measurement { get; set; }

    public override string TableName => "onvif_packets";
    
    public override void WriteColumns(ISender sender)
    {
        sender.Column("type", Type);
        sender.Column("description", Description);
        if (Zoom.HasValue)
            sender.Column("zoom", Zoom.Value);
        sender.Column("measurement", Measurement);
    }
}