using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Utils.Parsers;

/// <summary>
/// Mapper class that routes packet parsing to the appropriate parser based on entity type and protocol
/// </summary>
public static class ParseMapper
{
    /// <summary>
    /// Maps raw packet data to the appropriate entity type using the correct parser
    /// This method automatically determines the protocol based on the entity type
    /// </summary>
    /// <typeparam name="T">The entity type to parse</typeparam>
    /// <param name="rawPacket">Raw packet bytes</param>
    /// <returns>Parsed entity of type T or null if parsing fails</returns>
    public static T? Map<T>(ReadOnlySpan<byte> rawPacket) where T : class
    {
        return typeof(T) switch
        {
            var t when t == typeof(MotionPacketEntity) => MotionPacketParser.Parse(rawPacket) as T,
            var t when t == typeof(SafetyPacketEntity) => SafetyPacketParser.Parse(rawPacket) as T,
            var t when t == typeof(OnVIFPacketEntity) => OnVifPacketParser.Parse(rawPacket) as T,
            _ => null
        };
    }
}
