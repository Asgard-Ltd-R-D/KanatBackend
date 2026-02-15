using System.Buffers.Binary;
using Microsoft.Extensions.Logging;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Utils.Enums;
using static PacketProcessing.Utils.Parsers.SafetyUtilities.SafetyCommands;

namespace PacketProcessing.Utils.Parsers
{
    public class SafetyPacketParser
    {
        private readonly ILogger<SafetyPacketParser> _logger;

        public SafetyPacketParser(ILogger<SafetyPacketParser> logger)
        {
            _logger = logger;
        }

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

                // --- Determine Safety Type (PBE/SBE) ---
                SafetyTypes? safetyType = dstIp switch
                {
                    Constants.Constants.PBE_IP => SafetyTypes.PBE,
                    Constants.Constants.SBE_IP => SafetyTypes.SBE,
                    _ => null
                };

                if (safetyType == null)
                {
                    _logger.LogDebug("Unknown Safety Type or Destination IP: {DstIp}", dstIp);
                    return null;
                }

                // --- Lookups using the new SafetyRecords Dictionary ---
                // 1. Look up Command (DO) -> Key is (Value, Type)
                var doKey = ((int)doVal, safetyType.Value);
                string doDescr = SafetyRecords.TryGetValue(doKey, out var doRec) 
                    ? doRec.OpCodeDescription 
                    : $"0x{doVal:X4}";

                // 2. Look up State -> Key is (Value, SafetyTypes.STATE)
                var stateKey = ((int)stVal, SafetyTypes.STATE);
                string stDescr = SafetyRecords.TryGetValue(stateKey, out var stRec) 
                    ? stRec.OpCodeDescription 
                    : $"0x{stVal:X4}";

                string dataPipeName = safetyType.Value.ToString(); // "PBE" or "SBE"

                _logger.LogDebug("Parsed Safety Packet → Name: {Name}, DO: {DO}, STATE: {STATE}", dataPipeName, doDescr, stDescr);

                return new SafetyPacketEntity
                {
                    Id = Guid.NewGuid(),
                    Timestamp = DateTime.UtcNow,
                    IsCmd = true,
                    Name = dataPipeName,
                    OpCode = $"0x{doVal:X4}",
                    Description = doDescr,
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