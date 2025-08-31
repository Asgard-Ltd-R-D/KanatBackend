using PacketProcessing.Entities.Packet;
using System.Collections.Generic;

namespace PacketProcessing.Utils;

/// <summary>
/// Protocol types for packet parsing
/// </summary>
public enum Protocol
{
    TCP,
    UDP,
    HTTP,
    HTTPS,
    MQTT,
    CoAP
}

/// <summary>
/// Static parser methods for different packet types and protocols
/// </summary>
public static class Parsers
{
    /// <summary>
    /// TCP parser for motion packets
    /// </summary>
    public static class TcpParser
    {
        /// <summary>
        /// Parses raw packet data into a MotionPacketEntity
        /// </summary>
        /// <param name="rawPacket">Raw packet bytes</param>
        /// <returns>Parsed MotionPacketEntity or null if parsing fails</returns>
        internal static MotionPacketEntity ParseMotionPacket(ReadOnlySpan<byte> rawPacket)
        {
            // TODO: Implement TCP packet parsing logic
            return null!;
        }
    }

    /// <summary>
    /// UDP parser for safety packets
    /// </summary>
    public static class UdpParser
    {
        /// <summary>
        /// Parses raw packet data into a SafetyPacketEntity
        /// </summary>
        /// <param name="rawPacket">Raw packet bytes</param>
        /// <returns>Parsed SafetyPacketEntity or null if parsing fails</returns>
        internal static SafetyPacketEntity ParseSafetyPacket(ReadOnlySpan<byte> rawPacket)
        {
            // TODO: Implement UDP packet parsing logic
            return null!;
        }
    }

    /// <summary>
    /// HTTP parser for OnVIF packets
    /// </summary>
    public static class HttpParser
    {
        /// <summary>
        /// Parses raw packet data into an OnVIFPacketEntity
        /// </summary>
        /// <param name="rawPacket">Raw packet bytes</param>
        /// <returns>Parsed OnVIFPacketEntity or null if parsing fails</returns>
        internal static OnVIFPacketEntity ParseOnVifPacket(ReadOnlySpan<byte> rawPacket)
        {
            // TODO: Implement HTTP packet parsing logic
            return null!;
        }
    }

    /// <summary>
    /// Public map that routes to the appropriate parser based on protocol and entity type
    /// </summary>
    /// <typeparam name="T">The entity type to parse</typeparam>
    /// <param name="protocol">The protocol to use for parsing</param>
    /// <param name="rawPacket">Raw packet bytes</param>
    /// <returns>Parsed entity of type T or null if parsing fails</returns>
    public static T? Map<T>(Protocol protocol, ReadOnlySpan<byte> rawPacket) where T : class
    {
        return (protocol, typeof(T)) switch
        {
            (Protocol.TCP, var t) when t == typeof(MotionPacketEntity) => TcpParser.ParseMotionPacket(rawPacket) as T,
            (Protocol.UDP, var t) when t == typeof(SafetyPacketEntity) => UdpParser.ParseSafetyPacket(rawPacket) as T,
            (Protocol.HTTP, var t) when t == typeof(OnVIFPacketEntity) => HttpParser.ParseOnVifPacket(rawPacket) as T,
            (Protocol.HTTPS, var t) when t == typeof(OnVIFPacketEntity) => HttpParser.ParseOnVifPacket(rawPacket) as T, // HTTPS uses same parser as HTTP
            _ => null
        };
    }

    /// <summary>
    /// Public map that routes to the appropriate parser based on string protocol name and entity type
    /// This method automatically converts string protocol names to Protocol enum values
    /// </summary>
    /// <typeparam name="T">The entity type to parse</typeparam>
    /// <param name="protocolString">The protocol name as string (e.g., "tcp", "udp", "http")</param>
    /// <param name="rawPacket">Raw packet bytes</param>
    /// <returns>Parsed entity of type T or null if parsing fails</returns>
    public static T? Map<T>(string protocolString, ReadOnlySpan<byte> rawPacket) where T : class
    {
        // Convert string protocol to enum (case-insensitive)
        if (!Enum.TryParse<Protocol>(protocolString, true, out var protocol))
        {
            return null; // Invalid protocol string
        }

        // Route to the enum-based Map method
        return Map<T>(protocol, rawPacket);
    }
}
