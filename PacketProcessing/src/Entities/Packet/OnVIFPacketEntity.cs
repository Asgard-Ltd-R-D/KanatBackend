using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using QuestDB.Senders;

namespace PacketProcessing.Entities.Packet;

[Table("onvif_packets")]
public class OnVIFPacketEntity : BasePacketEntity
{   
    [Column("description")]
    [StringLength(128)]
    public required string Description { get; set; }
    
    [Column("zoom")]
    public float? Zoom { get; set; }
    
    [Column("measurement")]
    public float? Measurement { get; set; }

    public override string TableName => "onvif_packets";
    
    public override void WriteColumns(ISender sender)
    {
        sender.Column("isCmd", IsCmd);
        sender.Column("description", Description);
        //Applicable for DAY/IR
        if (Zoom.HasValue)
            sender.Column("zoom", Zoom.Value);
        else
            sender.NullableColumn("zoom", float.NaN);

        //Applicable for LRF/LRF
        if (Measurement.HasValue)
            sender.Column("measurement", Measurement.Value);
        else
            sender.NullableColumn("measurement", float.NaN);
    }
}
