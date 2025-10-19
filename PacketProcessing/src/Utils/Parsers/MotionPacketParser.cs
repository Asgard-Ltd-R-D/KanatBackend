using PacketProcessing.Entities.Packet;
using System.Buffers.Binary;
using Microsoft.Extensions.Logging;
using PacketProcessing.Utils.Parsers.MotionUtilities;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Utils.Parsers;

/// <summary>
/// Parser for Motion packets using TCP/CapTrack protocol
/// </summary>
public static class MotionPacketParser
{
    private static ILogger? _logger;

   
    public static void SetLogger(ILogger logger)
    {
        _logger = logger;
    }
    private const string REPORT_IP = "132.8.7.125";

    /// <summary>
    /// Parses raw packet data into a MotionPacketEntity by following these conventions:
    /// - [0..1]=StartByte (u16),
    /// - [2]=Length (u8),
    /// - [3]=GroupID (u8),
    /// - [4]=AxisID (u8),
    /// - [5..6]=OPCODE (u16, big-endian, combined withe high opcode and low opcode),
    /// - [7..7+N-1]=DATA (N = Length-4),
    /// - [7+N]=Checksum (u8),
    /// </summary>
    /// <param name="rawPacket">Raw packet bytes</param>
    /// <returns>Parsed MotionPacketEntity or null if parsing fails</returns>
    public static MotionPacketEntity? Parse(ReadOnlySpan<byte> rawPacket)
    {
        try
        {
            // --- Check if the packet is long enough to contain an Ethernet + IP + TCP/CapTrack Data Payload ---
            if (rawPacket.Length < 54)
            {
                _logger?.LogWarning("Packet too short to contain an Ethernet + IP + TCP/CapTrack Data Payload. Raw Packet Length: {RawPacketLength}", rawPacket.Length);
                return null;
            }

            // Ethernet → IP start calculation
            int ipStart = (rawPacket.Length >= 14 && BinaryPrimitives.ReadUInt16BigEndian(rawPacket.Slice(12, 2)) == 0x0800) ? 14 : 0;

            // IPv4 sanity check
            if (rawPacket.Length < ipStart + 20 || (rawPacket[ipStart] >> 4) != 4)
                return null;

            // IP header length calculation
            int ipHeaderLen = (rawPacket[ipStart] & 0x0F) * 4;
            if (ipHeaderLen < 20 || rawPacket.Length < ipStart + ipHeaderLen)
                return null;

            // TCP start calculation
            int tcpStart = ipStart + ipHeaderLen;
            if (rawPacket.Length < tcpStart + 20)
                return null;

            // TCP header length calculation
            int tcpHeaderLen = ((rawPacket[tcpStart + 12] >> 4) & 0x0F) * 4;
            if (tcpHeaderLen < 20)
                tcpHeaderLen = 20;

            // TCP payload start calculation
            int tcpPayloadStart = tcpStart + tcpHeaderLen;
            if (tcpPayloadStart >= rawPacket.Length)
            {
                _logger?.LogDebug("No TCP payload (start={Start}, total={Total})", tcpPayloadStart, rawPacket.Length);
                return null;
            }

            // Extract the TCP payload
            ReadOnlySpan<byte> tcpPayload = rawPacket[tcpPayloadStart..];

            int payloadLen = tcpPayload.Length;
            _logger?.LogDebug("TCP payload starts at {TcpPayloadStart}, length = {PayloadLen} bytes", tcpPayloadStart, payloadLen);

            if (payloadLen < 7)
            {
                _logger?.LogDebug("Payload too small ({Len} bytes), dropping packet", payloadLen);
                return null;
            }

            // --- Source IP ---
            var srcIp = $"{rawPacket[ipStart + 12]}.{rawPacket[ipStart + 13]}.{rawPacket[ipStart + 14]}.{rawPacket[ipStart + 15]}";
            bool isReport = srcIp == REPORT_IP;

            // --- Packet fields with safety checks ---
            byte length = tcpPayload.Length >= 3 ? tcpPayload[2] : (byte)0;
            byte axisId = tcpPayload.Length >= 5 ? tcpPayload[4] : (byte)0;

            // Opcode extraction, high opcode and low opcode combined into one ushort
            ushort opCode = tcpPayload.Length >= 7
                ? BinaryPrimitives.ReadUInt16BigEndian(tcpPayload.Slice(5, 2))
                : (ushort)0;

            // --- Data Section, can be varying length depending on the opcode ---
            ReadOnlySpan<byte> captureData = tcpPayload.Length > 9
                ? tcpPayload[7..^1] // Slice from 7 to the second last byte (checksum)
                : [];

            var opDesc = MotionCommands.MotionRecords.TryGetValue(opCode, out var desc) ? desc.OpCodeDescription : null;
            if (opDesc == null)
            {
                _logger?.LogDebug("Unknown opcode: {opCode}, dropping packet", opCode);
                return null;
            }
            double? value = DecodeValue(captureData, opCode, !isReport);

            if (value.HasValue)
            {
                _logger?.LogDebug("Parsed Motion Packet → Axis: {Axis}, Opcode: {opCode} ({opDesc}), Value: {Value}, IsCmd: {IsCmd}", axisId, opCode, opDesc, value, !isReport);
            }
            else
            {
                _logger?.LogDebug("Parsed Motion Packet → Axis: {Axis}, Opcode: {opCode} ({opDesc}), IsCmd: {IsCmd}, has no value, dropping packet", axisId, opCode, opDesc, !isReport);
                return null;
            }

            return new MotionPacketEntity
            {
                Id = Guid.NewGuid(),
                Timestamp = DateTime.UtcNow,
                Axis = axisId,
                OpCode = $"0x{opCode:X4}",
                OpCodeDescription = opDesc,
                Value = value,
                IsCmd = !isReport
            };
        }
        catch (Exception ex)
        {
            _logger?.LogError(ex, "Error parsing motion packet. Exception: {ExceptionMessage}, Length: {Length} bytes, dropping packet", ex.Message, rawPacket.Length);
            return null;
        }
    }

    private static double DecodeValue(ReadOnlySpan<byte> rawPacket, int opCode, bool isCmd)
    {       
        if (MotionCommands.MotionRecords.TryGetValue(opCode, out var motionRecord))
        {
            if (isCmd)
            {
                return motionRecord.Send switch
                {
                    ValueTypes.UInt8 => rawPacket[0], // uint8
                    ValueTypes.UInt16BE => BinaryPrimitives.ReadUInt16BigEndian(rawPacket), // uint16
                    ValueTypes.UInt32BE => BinaryPrimitives.ReadUInt32BigEndian(rawPacket), // 32-bit float big-endian
                    ValueTypes.None => 1d, // return 1d, which means the packet has been appeared but the value is not available
                    _ => double.NaN, // None of the value type is matching the opcode return NaN and drop the packet
                };
            }
            else
            {
                return motionRecord.Return switch
                {
                    ValueTypes.UInt8 => rawPacket[0], // uint8
                    ValueTypes.UInt16BE => BinaryPrimitives.ReadUInt16BigEndian(rawPacket), // uint16
                    ValueTypes.UInt32BE => BinaryPrimitives.ReadUInt32BigEndian(rawPacket), // 32-bit float big-endian
                    ValueTypes.None => 1d, // return 1d, which means the packet has been appeared but the value is not available
                    _ => double.NaN, // None of the value type is matching the opcode return NaN and drop the packet
                };
            }
        }
        return double.NaN;
    }
}
