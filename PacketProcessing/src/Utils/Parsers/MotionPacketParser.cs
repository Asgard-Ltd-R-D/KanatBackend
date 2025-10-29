using PacketProcessing.Entities.Packet;
using System.Buffers.Binary;
using Microsoft.Extensions.Logging;
using PacketProcessing.Utils.Parsers.MotionUtilities;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Utils.Parsers;

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
public class MotionPacketParser
{
    private readonly ILogger<MotionPacketParser> _logger;

    public MotionPacketParser(ILogger<MotionPacketParser> logger)
    {
        _logger = logger;
    }

    public MotionPacketEntity? Parse(ReadOnlySpan<byte> rawPacket)
    {
        try
        {
            // --- Try to locate an IPv4 header dynamically (0x45 = IPv4 + IHL=5) ---
            int ipStart = -1;
            for (int i = 0; i < Math.Min(32, rawPacket.Length - 20); i++)
            {
                // IPv4 header signature: 0x45 (version=4, IHL=5)
                if (rawPacket[i] == 0x45 && rawPacket.Length > i + 20)
                {
                    ipStart = i;
                    break;
                }
            }

            ReadOnlySpan<byte> payload = [];
            ushort srcPort = 0;
            ushort dstPort = 0;

            if (ipStart >= 0 && rawPacket.Length >= ipStart + 40)
            {
                // Case 1: IP header detected → parse full IP+TCP structure
                _logger.LogTrace("Detected IPv4 header at offset {Offset}", ipStart);
                payload = ExtractTcpPayload(rawPacket, ipStart, out srcPort, out dstPort);
                if (payload.IsEmpty)
                {
                    _logger.LogDebug("Failed to extract TCP payload (ipStart={Start})", ipStart);
                    return null;
                }
            }
            else
            {
                // Case 2: No IPv4 → still attempt to parse TCP header directly
                _logger.LogTrace("No IPv4 header found; assuming TCP header starts at offset 0.");

                if (rawPacket.Length >= 20)
                {
                    srcPort = BinaryPrimitives.ReadUInt16BigEndian(rawPacket.Slice(0, 2));
                    dstPort = BinaryPrimitives.ReadUInt16BigEndian(rawPacket.Slice(2, 2));
                    int tcpHeaderLen = ((rawPacket[12] >> 4) & 0x0F) * 4;
                    int tcpPayloadStart = tcpHeaderLen;

                    if (tcpPayloadStart < rawPacket.Length)
                        payload = rawPacket[tcpPayloadStart..];
                }

                // If even that fails (e.g., truncated), fallback to raw payload
                if (payload.IsEmpty)
                {
                    _logger.LogTrace("TCP header parse failed; using entire packet as payload.");
                    payload = rawPacket;
                }
            }

            if (payload.Length < 7)
            {
                _logger.LogDebug("Payload too small ({Len} bytes), dropping packet.", payload.Length);
                return null;
            }

            bool isReport = srcPort == Constants.Constants.MOTION_REPORT_PORT;

            // --- Field extraction ---
            byte length = payload.Length >= 3 ? payload[2] : (byte)0;
            byte axisId = payload.Length >= 5 ? payload[4] : (byte)0;
            // Opcode extraction, high opcode and low opcode combined into one ushort
            ushort opCode = payload.Length >= 7
                ? BinaryPrimitives.ReadUInt16BigEndian(payload.Slice(5, 2))
                : (ushort)0;

            if (!MotionCommands.MotionRecords.TryGetValue(opCode, out var record))
            {
                _logger.LogDebug("Unknown opcode: 0x{OpCode:X4}, dropping packet.", opCode);
                return null;
            }
            // --- Data Section, can be varying length depending on the opcode ---
            ReadOnlySpan<byte> captureData = payload.Length > 8 ? payload[7..^1] : [];
            double value = DecodeValue(captureData, opCode, !isReport);
            if (double.IsNaN(value))
            {
                _logger.LogDebug("Opcode 0x{OpCode:X4} has no decodable value, dropping packet.", opCode);
                return null;
            }

            _logger.LogDebug(
                "Parsed Motion Packet → Axis={Axis}, Opcode=0x{Op:X4} ({Desc}), Value={Val}, SrcPort={Src}, DstPort={Dst}, IsCmd={IsCmd}",
                axisId, opCode, record.OpCodeDescription, value, srcPort, dstPort, !isReport);

            return new MotionPacketEntity
            {
                Id = Guid.NewGuid(),
                Timestamp = DateTime.UtcNow,
                Axis = axisId,
                OpCode = $"0x{opCode:X4}",
                Description = record.OpCodeDescription,
                Value = value,
                IsCmd = !isReport
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error parsing motion packet ({Length} bytes)", rawPacket.Length);
            return null;
        }
    }

    // --- Extract TCP payload from IP+TCP frame ---
    private static ReadOnlySpan<byte> ExtractTcpPayload(ReadOnlySpan<byte> raw, int ipStart, out ushort srcPort, out ushort dstPort)
    {
        srcPort = 0;
        dstPort = 0;

        // Validate minimal IP header
        int ipHeaderLen = (raw[ipStart] & 0x0F) * 4;
        if (raw.Length < ipStart + ipHeaderLen + 20)
            return [];

        int tcpStart = ipStart + ipHeaderLen;
        int tcpHeaderLen = ((raw[tcpStart + 12] >> 4) & 0x0F) * 4;
        int tcpPayloadStart = tcpStart + tcpHeaderLen;
        if (tcpPayloadStart >= raw.Length)
            return [];

        srcPort = BinaryPrimitives.ReadUInt16BigEndian(raw.Slice(tcpStart, 2));
        dstPort = BinaryPrimitives.ReadUInt16BigEndian(raw.Slice(tcpStart + 2, 2));

        return raw[tcpPayloadStart..];
    }

    // --- Decode value according to opcode metadata ---
    private double DecodeValue(ReadOnlySpan<byte> data, int opCode, bool isCmd)
    {
        if (!MotionCommands.MotionRecords.TryGetValue(opCode, out var motionRecord))
            return double.NaN;

        var vt = isCmd ? motionRecord.Send : motionRecord.Return;

        return vt switch
        {
            ValueTypes.UInt8     => data.Length >= 1 ? data[0] : double.NaN,
            ValueTypes.UInt16BE  => data.Length >= 2 ? BinaryPrimitives.ReadUInt16BigEndian(data) : double.NaN, //uint16
            ValueTypes.UInt32BE  => data.Length >= 4 ? BinaryPrimitives.ReadUInt32BigEndian(data) : double.NaN, //32-bit integer in big-endian format
            ValueTypes.Float32BE => data.Length >= 4 ? BinaryPrimitives.ReadSingleBigEndian(data) : double.NaN, //32-bit float in big-endian format
            ValueTypes.None      => 1d, // return 1d, which means the packet has been appeared but the value is not available
            _                    => double.NaN //None of the value type is matching the opcode return NaN and drop the packet
        };
    }
}
