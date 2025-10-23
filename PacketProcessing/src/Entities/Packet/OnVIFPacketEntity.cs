using System.ComponentModel.DataAnnotations.Schema;
using PacketProcessing.Utils.Constants;
using PacketProcessing.Utils.Enums;
using QuestDB.Senders;

namespace PacketProcessing.Entities.Packet;

[Table(Constants.ONVIF_PACKETS_TAG)]
public class OnVIFPacketEntity : BasePacketEntity
{   
    
    [Column("zoom")]
    public double? Zoom { get; set; }
    
    [Column("measurement")]
    public double? Measurement { get; set; }

    public override string TableName => Constants.ONVIF_PACKETS_TAG;
    
    public override void WriteColumns(ISender sender)
    {
        sender.Column("isCmd", IsCmd);
        sender.Column("description", Description);
        //Applicable for DAY/IR
        if (Zoom.HasValue)
            sender.Column("zoom", Zoom.Value);
        else
            sender.NullableColumn("zoom", double.NaN);

        //Applicable for LRF/LRF
        if (Measurement.HasValue)
            sender.Column("measurement", Measurement.Value);
        else
            sender.NullableColumn("measurement", double.NaN);
    }

    public override string GetSubscriptionKey()
    {
        return $"{DataPipes.OnVIF}|{Description}|{IsCmd}".ToLower();
    }
}
