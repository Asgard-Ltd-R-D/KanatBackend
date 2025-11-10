using PacketProcessing.DTOs.Data;
using PacketProcessing.Entities;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Utils.Parsers;

/// <summary>
/// Parser for converting packet entities to PlainDataDto
/// Extracts timestamp and a single numeric value from each packet type
/// </summary>
public static class PlainDataConverter
{
    /// <summary>
    /// Parse a single entity into PlainDataDto
    /// Uses type-specific logic to extract the numeric value
    /// </summary>
    public static PlainDataDto? Convert<T>(T entity) where T : BasePacketEntity
    {
        return entity switch
        {
            MotionPacketEntity motion => ConvertMotion(motion),
            SafetyPacketEntity safety => ConvertSafety(safety),
            OnVIFPacketEntity onvif => ConvertOnVIF(onvif),
            _ => null
        };
    }

    /// <summary>
    /// Parse MotionPacketEntity to PlainDataDto
    /// Uses Value as the value, defaults to 0 if null
    /// </summary>
    private static PlainDataDto ConvertMotion(MotionPacketEntity motion)
    {
        // Applicable for Motion Commands that have a float value
        if (!motion.IsCmd && motion.Value.HasValue) 
            return new PlainDataDto
            {
                Timestamp = new DateTimeOffset(motion.Timestamp).ToUnixTimeMilliseconds(),
                Value = motion.Value.Value,
                SubscriptionKey = motion.GetSubscriptionKey()
            };
        // Applicable for Motion Commands that have no float value
        if (motion.IsCmd)
            return new PlainDataDto
            {
                Timestamp = new DateTimeOffset(motion.Timestamp).ToUnixTimeMilliseconds(),
                Value = 1d,
                SubscriptionKey = motion.GetSubscriptionKey()
            };
        // Damaged packet
        return new PlainDataDto
        {
            Timestamp = new DateTimeOffset(motion.Timestamp).ToUnixTimeMilliseconds(),
            Value = motion.Value ?? -1d,
            SubscriptionKey = motion.GetSubscriptionKey()
        };
    }

    /// <summary>
    /// Parse SafetyPacketEntity to PlainDataDto
    /// Uses Type as the value (true=1, false=0)
    /// Alternative: could parse State string to numeric value
    /// </summary>
    private static PlainDataDto ConvertSafety(SafetyPacketEntity safety)
    {
        return new PlainDataDto
        {
            Timestamp = new DateTimeOffset(safety.Timestamp).ToUnixTimeMilliseconds(),
            Value = safety.State switch
            {
                "ON" => 1d,
                "OFF" => 0d,
                "PULSE" => 2d,
                "BURST" => 3d,
                _ => -1d
            },
            SubscriptionKey = safety.GetSubscriptionKey()
        };
    }

    /// <summary>
    /// Parse OnVIFPacketEntity to PlainDataDto
    /// Uses Measurement as the value
    /// </summary>
    private static PlainDataDto ConvertOnVIF(OnVIFPacketEntity onvif)
    {
        switch (onvif.Description)
        {
            case Constants.Constants.ONVIF_FOV_REQ:
                return new PlainDataDto
                {
                    Timestamp = new DateTimeOffset(onvif.Timestamp).ToUnixTimeMilliseconds(),
                    Value = 1.0d,
                    SubscriptionKey = onvif.GetSubscriptionKey()
                };
            case Constants.Constants.ONVIF_FOV_STS:
                return new PlainDataDto
                {
                    Timestamp = new DateTimeOffset(onvif.Timestamp).ToUnixTimeMilliseconds(),
                    Value = onvif.Zoom ?? -1.0d,
                    SubscriptionKey = onvif.GetSubscriptionKey()
                };
            case Constants.Constants.ONVIF_LRF_REQ:
                return new PlainDataDto
                {
                    Timestamp = new DateTimeOffset(onvif.Timestamp).ToUnixTimeMilliseconds(),
                    Value = 1.0d,
                    SubscriptionKey = onvif.GetSubscriptionKey()
                };
            case Constants.Constants.ONVIF_LRF_STS:
                return new PlainDataDto
                {
                    Timestamp = new DateTimeOffset(onvif.Timestamp).ToUnixTimeMilliseconds(),
                    Value = onvif.Measurement ?? -1.0d,
                    SubscriptionKey = onvif.GetSubscriptionKey()
                };
        }
        return new PlainDataDto
        {
            Timestamp = new DateTimeOffset(onvif.Timestamp).ToUnixTimeMilliseconds(),
            Value = -1.0d,
            SubscriptionKey = onvif.GetSubscriptionKey()
        };
    }
}
