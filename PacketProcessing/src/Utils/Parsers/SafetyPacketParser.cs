using System.Buffers.Binary;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Utils.Parsers
{
    public static class SafetyPacketParser
    {
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
            if (raw.Length < 20) return null;

            // --- Find IPv4 header (with or without Ethernet) ---
            int ipStart;
            if (raw.Length >= 14 && ReadBE16(raw.Slice(12, 2)) == 0x0800) // Ethernet + IPv4
                ipStart = 14;
            else if (raw.Length >= 20 && (raw[0] >> 4) == 4)              // Raw IPv4
                ipStart = 0;
            else
                return null;

            if (raw.Length < ipStart + 20) return null;

            int ihl = (raw[ipStart] & 0x0F) * 4;
            if (ihl < 20 || raw.Length < ipStart + ihl) return null;

            if (raw[ipStart + 9] != 17) return null; // UDP only

            // Destination IP (for DO map choice)
            var dstIp = $"{raw[ipStart + 16]}.{raw[ipStart + 17]}.{raw[ipStart + 18]}.{raw[ipStart + 19]}";

            // --- UDP header ---
            int udpStart = ipStart + ihl;
            if (raw.Length < udpStart + 8) return null;

            ushort udpLen = ReadBE16(raw.Slice(udpStart + 4, 2));
            if (udpLen < 8) return null;

            int payloadStart = udpStart + 8;
            int available = raw.Length - payloadStart;
            int payloadLen = Math.Min(udpLen - 8, available);
            if (payloadLen < 20) return null;

            // --- Safety PDU is the last 20 bytes of the UDP payload ---
            var pdu = raw.Slice(payloadStart + payloadLen - 20, 20);

            // Offsets in the 20-byte PDU
            // 16..17 = DO (BE), 18..19 = STATE (BE)
            ushort doVal = ReadBE16(pdu.Slice(16, 2));
            ushort stVal = ReadBE16(pdu.Slice(18, 2));

            // Choose DO map by destination IP
            IReadOnlyDictionary<ushort, string>? doMap = dstIp switch
            {
                "132.8.7.101" => DO_PBE,
                "132.8.7.102" => DO_SBE,
                "127.0.0.1"   => DO_SBE, // convenient local fallback
                _             => null
            };

            string doDescr = (doMap != null && doMap.TryGetValue(doVal, out var name)) ? name : $"0x{doVal:X4}";
            string stDescr = STATE.TryGetValue(stVal, out var sname) ? sname : $"0x{stVal:X4}";

            // Type: true for PBE, false otherwise (match your earlier convention)
            bool type = dstIp == "132.8.7.101";

            return new SafetyPacketEntity
            {
                Id = Guid.NewGuid(),
                Timestamp = DateTime.UtcNow,
                Type = type,
                OpCode = doVal.ToString(),
                OpCodeDescription = doDescr,
                State = stDescr
            };
        }

        private static ushort ReadBE16(ReadOnlySpan<byte> s) =>
            BinaryPrimitives.ReadUInt16BigEndian(s);
    }
}
