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
                Timestamp = motion.Timestamp,
                Value = motion.Value.Value,
                DataPipe = DataPipes.Motion,
                MethodName = motion.Description
            };
        // Applicable for Motion Commands that have no float value
        if (motion.IsCmd)
            return new PlainDataDto
            {
                Timestamp = motion.Timestamp,
                Value = 1d,
                DataPipe = DataPipes.Motion,
                MethodName = motion.Description
            };
        // Damaged packet
        return new PlainDataDto
        {
            Timestamp = motion.Timestamp,
            Value = motion.Value ?? -1d,
            DataPipe = DataPipes.Motion,
            MethodName = motion.Description
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
            Timestamp = safety.Timestamp,
            Value = safety.State switch
            {
                "ON" => 1d,
                "OFF" => 0d,
                "PULSE" => 2d,
                "BURST" => 3d,
                _ => -1d
            },
            DataPipe = DataPipes.Safety,
            MethodName = safety.Description
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
                    Timestamp = onvif.Timestamp,
                    Value = 1.0d,
                    DataPipe = DataPipes.OnVIF,
                    MethodName = onvif.Description
                };
            case Constants.Constants.ONVIF_FOV_STS:
                return new PlainDataDto
                {
                    Timestamp = onvif.Timestamp,
                    Value = onvif.Zoom ?? -1.0d,
                    DataPipe = DataPipes.OnVIF,
                    MethodName = onvif.Description
                };
            case Constants.Constants.ONVIF_LRF_REQ:
                return new PlainDataDto
                {
                    Timestamp = onvif.Timestamp,
                    Value = 1.0d,
                    DataPipe = DataPipes.OnVIF,
                    MethodName = onvif.Description
                };
            case Constants.Constants.ONVIF_LRF_STS:
                return new PlainDataDto
                {
                    Timestamp = onvif.Timestamp,
                    Value = onvif.Measurement ?? -1.0d,
                    DataPipe = DataPipes.OnVIF,
                    MethodName = onvif.Description
                };
        }
        return new PlainDataDto
        {
            Timestamp = onvif.Timestamp,
            Value = -1.0d,
            DataPipe = DataPipes.OnVIF,
            MethodName = onvif.Description
        };
    }
}

