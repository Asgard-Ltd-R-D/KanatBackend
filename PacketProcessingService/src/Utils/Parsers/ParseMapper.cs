using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Utils.Parsers;

/// <summary>
/// Mapper class that routes packet parsing to the appropriate parser based on entity type and protocol
/// </summary>
public class ParseMapper
{
    private readonly MotionPacketParser _motionPacketParser;
    private readonly SafetyPacketParser _safetyPacketParser;
    private readonly OnVifPacketParser _onVifPacketParser;

    public ParseMapper(MotionPacketParser motionPacketParser, SafetyPacketParser safetyPacketParser, OnVifPacketParser onVifPacketParser)
    {
        _motionPacketParser = motionPacketParser;
        _safetyPacketParser = safetyPacketParser;
        _onVifPacketParser = onVifPacketParser;
    }
    /// <summary>
    /// Maps raw packet data to the appropriate entity type using the correct parser
    /// This method automatically determines the protocol based on the entity type
    /// </summary>
    /// <typeparam name="T">The entity type to parse</typeparam>
    /// <param name="rawPacket">Raw packet bytes</param>
    /// <returns>Parsed entity of type T or null if parsing fails</returns>
    public T? Map<T>(ReadOnlySpan<byte> rawPacket) where T : class
    {
        return typeof(T) switch
        {
            var t when t == typeof(MotionPacketEntity) => _motionPacketParser.Parse(rawPacket) as T,
            var t when t == typeof(SafetyPacketEntity) => _safetyPacketParser.Parse(rawPacket) as T,
            var t when t == typeof(OnVIFPacketEntity) => _onVifPacketParser.Parse(rawPacket) as T,
            _ => null
        };
    }
}