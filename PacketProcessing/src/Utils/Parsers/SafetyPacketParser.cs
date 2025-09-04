using PacketProcessing.Entities.Packet;
using System.Buffers.Binary;

namespace PacketProcessing.Utils.Parsers;

/// <summary>
/// Parser for Safety packets using UDP/Modbus-like protocol
/// </summary>
public static class SafetyPacketParser
{
    private static readonly IReadOnlyDictionary<ushort, string> DO_PBE = new Dictionary<ushort, string>
    {
        { 0x0010, "1" },
        { 0x0027, "DO3_FIRE1" },
        { 0x0012, "DO2_MOTION" },
        { 0x0014, "DO4_LED_FIRE_EN" }
    };

    private static readonly IReadOnlyDictionary<ushort, string> DO_SBE = new Dictionary<ushort, string>
    {
        { 0x0010, "DO0_RLD" },
        { 0x0011, "DO1_RLD_SFTY" },
        { 0x0012, "DO2_PWR" },
        { 0x0028, "DO4_FIRE2" },
        { 0x0015, "X5" }
    };

    private static readonly IReadOnlyDictionary<ushort, string> STATE = new Dictionary<ushort, string>
    {
        { 0x0000, "OFF" },
        { 0xFF00, "ON" },
        { 0x0001, "PULSE" },
        { 0x0003, "BURST" }
    };

    /// <summary>
    /// Parses raw packet data into a SafetyPacketEntity
    /// </summary>
    /// <param name="rawPacket">Raw packet bytes</param>
    /// <returns>Parsed SafetyPacketEntity or null if parsing fails</returns>
    public static SafetyPacketEntity? Parse(ReadOnlySpan<byte> rawPacket)
    {
        // ---- Ethernet ----
        if (rawPacket.Length < 14) return null;
        int offset;

        // EtherType (with VLAN/QinQ handling)
        ushort ethType = ReadBE16(rawPacket[12..]);
        offset = 14;

        // VLAN (0x8100) / QinQ (0x88A8)
        if (ethType == 0x8100 || ethType == 0x88A8)
        {
            if (rawPacket.Length < offset + 4) return null;
            ethType = ReadBE16(rawPacket[(offset + 2)..]);
            offset += 4;
        }

        // ---- IPv4 only (0x0800) ----
        if (ethType != 0x0800) return null;
        if (rawPacket.Length < offset + 20) return null; // min IPv4 header

        var ipStart = offset;
        byte verIhl = rawPacket[ipStart];
        int version = verIhl >> 4;
        if (version != 4) return null;

        int ihlBytes = (verIhl & 0x0F) * 4;
        if (ihlBytes < 20) return null;
        if (rawPacket.Length < ipStart + ihlBytes) return null;

        byte protocol = rawPacket[ipStart + 9];
        if (protocol != 17) return null; // UDP

        // Source/Dest IPs
        var dstIpSpan = rawPacket.Slice(ipStart + 16, 4);
        string dstIp = ToIPv4(dstIpSpan);

        // ---- UDP ----
        int udpStart = ipStart + ihlBytes;
        if (rawPacket.Length < udpStart + 8) return null;

        // UDP length check (optional but nice)
        ushort udpLen = ReadBE16(rawPacket[(udpStart + 4)..]);
        if (udpLen < 8) return null;
        if (rawPacket.Length < udpStart + udpLen) return null;

        int pduStart = udpStart + 8;
        int pduLen = udpLen - 8;
        var pdu = rawPacket.Slice(pduStart, pduLen);

        // ---- SAFETY/Modbus-like PDU ----
        // Layout:
        // 0..1  TID
        // 2..3  PID
        // 4..5  Length  (UnitID + FC + DataN)
        // 6     UnitID
        // 7     FunctionCode
        // 8..9  param1
        // 10..11 param2
        // 12..13 param3
        // 14..15 param4
        // 16..17 DO
        // 18..19 STATE
        if (pdu.Length < 20) return null;

        // Extract DO/STATE codes (big-endian)
        ushort doCode = ReadBE16(pdu.Slice(16, 2));
        ushort stateCode = ReadBE16(pdu.Slice(18, 2));

        bool isPbe = dstIp == "132.8.7.101";
        bool isSbe = dstIp == "132.8.7.102";
        IReadOnlyDictionary<ushort, string>? doMap =
            isPbe ? DO_PBE :
            isSbe ? DO_SBE : null;
        
        string doText = doMap != null && doMap.TryGetValue(doCode, out var doName)
            ? doName
            : $"0x{doCode:X4}";

        string stateText = STATE.TryGetValue(stateCode, out var stName)
            ? stName
            : $"0x{stateCode:X4}";

        // Build entity
        return new SafetyPacketEntity
        {
            Id = Guid.NewGuid(),
            Timestamp = DateTime.UtcNow,
            Type = isPbe,
            OpCode = doCode.ToString(),
            OpCodeDescription = doText,
            State = stateText
        };
    }

    private static ushort ReadBE16(ReadOnlySpan<byte> s) => 
        BinaryPrimitives.ReadUInt16BigEndian(s);

    private static string ToIPv4(ReadOnlySpan<byte> s) =>
        $"{s[0]}.{s[1]}.{s[2]}.{s[3]}";
}
