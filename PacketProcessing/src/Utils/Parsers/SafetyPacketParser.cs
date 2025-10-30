using System.Buffers.Binary;
using Microsoft.Extensions.Logging;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Utils.Parsers
{
    public class SafetyPacketParser
    {
        private readonly ILogger<SafetyPacketParser> _logger;

        public SafetyPacketParser(ILogger<SafetyPacketParser> logger)
        {
            _logger = logger;
        }

        // DO maps (by destination IP)
        private readonly IReadOnlyDictionary<ushort, string> DO_PBE = new Dictionary<ushort, string>
        {
            { 0x0010, "1" },
            { 0x0027, "DO3_FIRE1" },
            { 0x0012, "DO2_MOTION" },
            { 0x0014, "DO4_LED_FIRE_EN" }
        };

        private readonly IReadOnlyDictionary<ushort, string> DO_SBE = new Dictionary<ushort, string>
        {
            { 0x0010, "DO0_RLD" },
            { 0x0011, "DO1_RLD_SFTY" },
            { 0x0012, "DO2_PWR" },
            { 0x0028, "DO4_FIRE2" },
            { 0x0015, "X5" }
        };

        private readonly IReadOnlyDictionary<ushort, string> STATE = new Dictionary<ushort, string>
        {
            { 0x0000, "OFF" },
            { 0xFF00, "ON" },
            { 0x0001, "PULSE" },
            { 0x0003, "BURST" }
        };

        public SafetyPacketEntity? Parse(ReadOnlySpan<byte> raw)
        {
            try
            {
                if (raw.Length < 4)
                {
                    _logger.LogDebug("Packet too short ({Len} bytes), dropping.", raw.Length);
                    return null;
                }

                // --- Try to locate the real IPv4 header start dynamically (0..31) ---
                int ipStart = -1;
                for (int i = 0; i < Math.Min(32, raw.Length - 20); i++)
                {
                    // IPv4 header signature: 0x45 (version=4, IHL=5)
                    if (raw[i] == 0x45 && raw.Length >= i + 20)
                    {
                        ipStart = i;
                        break;
                    }
                }

                ReadOnlySpan<byte> payload;
                string srcIp = string.Empty;
                string dstIp = string.Empty;

                if (ipStart >= 0 && raw.Length >= ipStart + 28) // enough for IP(20) + UDP(8)
                {
                    _logger.LogTrace("Detected IPv4 header at offset {Offset}", ipStart);

                    payload = ExtractUdpPayload(raw, ipStart, out srcIp, out dstIp);
                    if (payload.IsEmpty)
                    {
                        _logger.LogDebug("Failed to extract UDP payload (ipStart={Start}), dropping.", ipStart);
                        return null;
                    }
                }
                else
                {
                    // No IPv4 signature detected → assume raw UDP payload (simulator)
                    _logger.LogTrace("No IPv4 header found; assuming raw UDP payload (simulator).");
                    payload = raw;
                    // dstIp stays empty; maps will fall back to "Unknown"
                }

                // --- Safety payload must end with: [ ... DO (2 bytes) | STATE (2 bytes) ] ---
                if (payload.Length < 4)
                {
                    _logger.LogDebug("Safety payload too small ({Len} bytes), dropping.", payload.Length);
                    return null;
                }

                int doOffset = payload.Length - 4;
                int stateOffset = payload.Length - 2;

                ushort doVal = ReadBE16(payload.Slice(doOffset, 2));
                ushort stVal = ReadBE16(payload.Slice(stateOffset, 2));

                // --- Map DO/STATE by destination IP when available ---
                IReadOnlyDictionary<ushort, string>? doMap = dstIp switch
                {
                    Constants.Constants.PBE_IP=> DO_PBE,
                    Constants.Constants.SBE_IP => DO_SBE,
                    _             => null
                };
                if (doMap == null)
                {
                    _logger.LogDebug("No DO map found for destination IP {DstIp}", dstIp);
                    return null;
                }

                string doDescr = (doMap != null && doMap.TryGetValue(doVal, out var name)) ? name : $"0x{doVal:X4}";
                string stDescr = STATE.TryGetValue(stVal, out var sname) ? sname : $"0x{stVal:X4}";

                var dataPipeName = dstIp switch
                {
                    Constants.Constants.PBE_IP => "PBE",
                    Constants.Constants.SBE_IP => "SBE",
                    _             => null
                };
                if (dataPipeName == null)
                {
                    _logger.LogDebug("No data pipe name found for destination IP {DstIp}", dstIp);
                    return null;
                }

                _logger.LogDebug("Parsed Safety Packet → Name: {Name}, DO: {DO}, STATE: {STATE}", dataPipeName, doDescr, stDescr);

                return new SafetyPacketEntity
                {
                    Id = Guid.NewGuid(),
                    Timestamp = DateTime.UtcNow, // your pipeline overrides with capture ts
                    IsCmd = true,
                    Name = dataPipeName,
                    OpCode = $"0x{doVal:X4}",   // HEX value of DO
                    Description = doDescr,      // DO description
                    State = stDescr
                };
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error parsing safety packet ({Length} bytes).", raw.Length);
                return null;
            }
        }

        // --- Extract UDP payload given the starting offset of the IPv4 header ---
        private static ReadOnlySpan<byte> ExtractUdpPayload(ReadOnlySpan<byte> raw, int ipStart, out string srcIp, out string dstIp)
        {
            srcIp = string.Empty;
            dstIp = string.Empty;

            if (raw.Length < ipStart + 20)
                return [];

            // Verify IPv4
            if ((raw[ipStart] >> 4) != 4)
                return [];

            int ihl = (raw[ipStart] & 0x0F) * 4;
            if (ihl < 20 || raw.Length < ipStart + ihl + 8)
                return [];

            // Protocol: UDP = 17
            byte proto = raw[ipStart + 9];
            if (proto != 17)
                return [];

            // IPs
            srcIp = $"{raw[ipStart + 12]}.{raw[ipStart + 13]}.{raw[ipStart + 14]}.{raw[ipStart + 15]}";
            dstIp = $"{raw[ipStart + 16]}.{raw[ipStart + 17]}.{raw[ipStart + 18]}.{raw[ipStart + 19]}";

            int udpStart = ipStart + ihl;
            if (raw.Length < udpStart + 8)
                return [];

            ushort udpLen = ReadBE16(raw.Slice(udpStart + 4, 2));
            if (udpLen < 8)
                return [];

            int payloadStart = udpStart + 8;
            int payloadLen = Math.Min(udpLen - 8, raw.Length - payloadStart);
            if (payloadLen <= 0)
                return [];

            return raw.Slice(payloadStart, payloadLen);
        }

        private static ushort ReadBE16(ReadOnlySpan<byte> s) =>
            BinaryPrimitives.ReadUInt16BigEndian(s);
    }
}
