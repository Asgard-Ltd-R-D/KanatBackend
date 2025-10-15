using System.Buffers.Binary;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Utils.Parsers
{
    public static class SafetyPacketParser
    {
        // Cache DO value strings to avoid allocations
        private static readonly Dictionary<ushort, string> DoValueStrings = new();
        private static readonly object _doValueLock = new();
        
        // DO maps (by destination IP)
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

    public static SafetyPacketEntity? Parse(ReadOnlySpan<byte> raw)
    {
        if (raw.Length < 42) return null; // Other UDP packet that is not Safety PDU

        // --- Detect IPv4 header (with Ethernet prefix if present) ---
        int ipStart = (raw.Length >= 14 && ReadBE16(raw.Slice(12, 2)) == 0x0800) ? 14 : 0;
        if (raw.Length < ipStart + 20 || (raw[ipStart] >> 4) != 4) return null;

        int ihl = (raw[ipStart] & 0x0F) * 4;
        if (ihl < 20 || raw.Length < ipStart + ihl) return null;

        if (raw[ipStart + 9] != 17) return null; // not UDP

        // --- Destination IP ---
        var dstIp = $"{raw[ipStart + 16]}.{raw[ipStart + 17]}.{raw[ipStart + 18]}.{raw[ipStart + 19]}";

        // --- UDP header ---
        int udpStart = ipStart + ihl;
        if (raw.Length < udpStart + 8) return null;

        ushort udpLen = ReadBE16(raw.Slice(udpStart + 4, 2));
        if (udpLen < 8) return null;

        int payloadStart = udpStart + 8;
        int payloadLen = Math.Min(udpLen - 8, raw.Length - payloadStart);
        if (payloadLen < 4) return null; // at least enough for DO + STATE

        // --- Extract DO (4 bytes from end) and STATE (last 2 bytes) ---
        int doOffset = payloadStart + payloadLen - 4;
        int stateOffset = payloadStart + payloadLen - 2;

        ushort doVal = ReadBE16(raw.Slice(doOffset, 2));
        ushort stVal = ReadBE16(raw.Slice(stateOffset, 2));

        // --- Map DO/STATE ---
        IReadOnlyDictionary<ushort, string>? doMap = dstIp switch
        {
            "132.8.7.101" => DO_PBE,
            "132.8.7.102" => DO_SBE,
            _             => null
        };

        string doDescr = (doMap != null && doMap.TryGetValue(doVal, out var name)) ? name : $"0x{doVal:X4}";
        string stDescr = STATE.TryGetValue(stVal, out var sname) ? sname : $"0x{stVal:X4}";

        return new SafetyPacketEntity
        {
            Id = Guid.NewGuid(),
            Timestamp=DateTime.UtcNow, // The datetime will be override by the actual timestamp of the packet
            Type = true,
            OpCode = doDescr,
            OpCodeDescription = doDescr,
            State = stDescr
        };
    }

        private static ushort ReadBE16(ReadOnlySpan<byte> s) =>
            BinaryPrimitives.ReadUInt16BigEndian(s);
    }
}
