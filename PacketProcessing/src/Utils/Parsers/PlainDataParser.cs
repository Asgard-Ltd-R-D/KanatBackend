using PacketProcessing.DTOs.Data;
using PacketProcessing.Entities;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Utils.Parsers;

/// <summary>
/// Parser for converting packet entities to PlainDataDto
/// Extracts timestamp and a single numeric value from each packet type
/// </summary>
public static class PlainDataParser
{
    /// <summary>
    /// Parse a single entity into PlainDataDto
    /// Uses type-specific logic to extract the numeric value
    /// </summary>
    public static PlainDataDto? Parse<T>(T entity) where T : BasePacketEntity
    {
        return entity switch
        {
            MotionPacketEntity motion => ParseMotion(motion),
            SafetyPacketEntity safety => ParseSafety(safety),
            OnVIFPacketEntity onvif => ParseOnVIF(onvif),
            _ => null
        };
    }

    /// <summary>
    /// Parse MotionPacketEntity to PlainDataDto
    /// Uses FloatValue as the value, defaults to 0 if null
    /// </summary>
    private static PlainDataDto ParseMotion(MotionPacketEntity motion)
    {
        // Applicable for Motion Commands that have a float value
        if (!motion.IsCmd && motion.FloatValue.HasValue) 
            return new PlainDataDto
            {
                Timestamp = motion.Timestamp,
                Value = motion.FloatValue.Value
            };
        // Applicable for Motion Commands that have no float value
        if (motion.IsCmd)
            return new PlainDataDto
            {
                Timestamp = motion.Timestamp,
                Value = 1f
            };
        // Damaged packet
        return new PlainDataDto
        {
            Timestamp = motion.Timestamp,
            Value = motion.FloatValue ?? -1f
        };
    }

    /// <summary>
    /// Parse SafetyPacketEntity to PlainDataDto
    /// Uses Type as the value (true=1, false=0)
    /// Alternative: could parse State string to numeric value
    /// </summary>
    private static PlainDataDto ParseSafety(SafetyPacketEntity safety)
    {
        return new PlainDataDto
        {
            Timestamp = safety.Timestamp,
            Value = safety.State switch
            {
                "ON" => 1f,
                "OFF" => 0f,
                "PULSE" => 2f,
                "BURST" => 3f,
                _ => -1f
            }
        };
    }

    /// <summary>
    /// Parse OnVIFPacketEntity to PlainDataDto
    /// Uses Measurement as the value
    /// </summary>
    private static PlainDataDto ParseOnVIF(OnVIFPacketEntity onvif)
    {
        if (onvif.Zoom.HasValue)
            return new PlainDataDto
            {
                Timestamp = onvif.Timestamp,
                Value = onvif.Zoom.Value
            };
        else if (onvif.Measurement.HasValue)
            return new PlainDataDto
            {
                Timestamp = onvif.Timestamp,
                Value = onvif.Measurement.Value
            };
        else
            return new PlainDataDto
            {
                Timestamp = onvif.Timestamp,
                Value = -1.0f
            };
    }
}

