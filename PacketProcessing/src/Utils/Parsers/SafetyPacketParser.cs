using PacketProcessing.Entities.Packet;
using System.Buffers.Binary;
using Microsoft.Extensions.Logging;

namespace PacketProcessing.Utils.Parsers;

/// <summary>
/// Parser for Safety packets using UDP/Modbus-like protocol
/// </summary>
public static class SafetyPacketParser
{
    private static ILogger? _logger;
    
    public static void SetLogger(ILogger logger)
    {
        _logger = logger;
    }
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
    /// Based on TypeScript implementation that parses the last 20 bytes as Safety PDU
    /// </summary>
    /// <param name="rawPacket">Raw packet bytes</param>
    /// <returns>Parsed SafetyPacketEntity or null if parsing fails</returns>
    public static SafetyPacketEntity? Parse(ReadOnlySpan<byte> rawPacket)
    {
        try
        {
            _logger?.LogDebug("Starting safety packet parsing. Packet length: {Length} bytes", rawPacket.Length);
            _logger?.LogDebug("Raw packet data: {Data}", BitConverter.ToString(rawPacket.ToArray()).Replace("-", ""));
            
            // ---- Parse full packet to extract destination IP ----
            if (rawPacket.Length < 34)
            {
                _logger?.LogWarning("Packet too short for safety parsing. Length: {Length} bytes, minimum required: 34", rawPacket.Length);
                return null; // Minimum Ethernet + IP + UDP header
            }
        
            // Check for different packet formats and headers
            int offset = 0;
            
            // Check for libpcap capture header (4 bytes) followed by IP header
            if (rawPacket.Length >= 8 && rawPacket[0] == 0x02 && rawPacket[4] == 0x45)
            {
                // Libpcap capture header (4 bytes) + IP header
                offset = 4;
                _logger?.LogDebug("Libpcap capture header detected (4-byte prefix)");
            }
            // Look for Ethernet header by checking if first bytes look like Ethernet
            else if (rawPacket.Length >= 14 && ReadBE16(rawPacket.Slice(12, 2)) == 0x0800)
            {
                // Standard Ethernet header
                offset = 14;
                _logger?.LogDebug("Standard Ethernet header detected");
            }
            else if (rawPacket.Length >= 20 && rawPacket[0] == 0x45) // IP header starts with 0x45 (Version 4, IHL 5)
            {
                // Loopback packet - no Ethernet header, starts directly with IP
                offset = 0;
                _logger?.LogDebug("Loopback packet detected (no Ethernet header)");
            }
            else
            {
                _logger?.LogWarning("Unknown packet format. First bytes: {FirstBytes}", BitConverter.ToString(rawPacket.Slice(0, Math.Min(20, rawPacket.Length)).ToArray()));
                return null;
            }
            
            // Verify we have enough data for IP header
            if (rawPacket.Length < offset + 20)
            {
                _logger?.LogWarning("Packet too short for IP header. Length: {Length}, required: {Required}", rawPacket.Length, offset + 20);
                return null; // Minimum IP header
            }
        
            // Parse IP header
            int ipStart = offset;
            byte verIhl = rawPacket[ipStart];
            int version = verIhl >> 4;
            int ihlBytes = (verIhl & 0x0F) * 4;
            _logger?.LogDebug("IP version: {Version}, IHL: {Ihl} bytes", version, ihlBytes);
            
            if (version != 4)
            {
                _logger?.LogWarning("Not IPv4 packet. Version: {Version}, expected: 4", version);
                return null;
            }
            
            if (ihlBytes < 20)
            {
                _logger?.LogWarning("Invalid IP header length. IHL: {Ihl} bytes, minimum: 20", ihlBytes);
                return null;
            }
            if (rawPacket.Length < ipStart + ihlBytes)
            {
                _logger?.LogWarning("Packet too short for IP header. Length: {Length}, required: {Required}", rawPacket.Length, ipStart + ihlBytes);
                return null;
            }
            
            // Extract destination IP
            string dstIp = ToIPv4(rawPacket.Slice(ipStart + 16, 4));
            _logger?.LogDebug("Destination IP: {DstIp}", dstIp);
            
            // Parse UDP header
            int udpStart = ipStart + ihlBytes;
            if (rawPacket.Length < udpStart + 8)
            {
                _logger?.LogWarning("Packet too short for UDP header. Length: {Length}, required: {Required}", rawPacket.Length, udpStart + 8);
                return null; // Minimum UDP header
            }
        
            // Extract the UDP payload
            int udpPayloadStart = udpStart + 8;
            if (udpPayloadStart + 20 > rawPacket.Length)
            {
                _logger?.LogWarning("Packet too short for UDP payload. Length: {Length}, required: {Required}", rawPacket.Length, udpPayloadStart + 20);
                return null;
            }
            
            // Get the UDP payload length
            ushort udpLength = ReadBE16(rawPacket.Slice(udpStart + 4, 2));
            int udpPayloadLength = udpLength - 8; // Subtract UDP header length
            _logger?.LogDebug("UDP length: {UdpLength}, payload length: {PayloadLength}", udpLength, udpPayloadLength);
            
            if (udpPayloadLength < 20)
            {
                _logger?.LogWarning("UDP payload too short for safety PDU. Payload length: {Length}, required: 20", udpPayloadLength);
                return null;
            }
            
            // Extract the Safety PDU from the UDP payload
            var pdu = rawPacket.Slice(rawPacket.Length - 20, 20);
            _logger?.LogDebug("Safety PDU (last 20 bytes): {Pdu}", BitConverter.ToString(pdu.ToArray()).Replace("-", ""));
        
            // ---- SAFETY/Modbus-like PDU (20 bytes) ----
            // Layout (based on TypeScript):
            // 0..1  TID (Transaction ID)
            // 2..3  PID (Protocol ID) 
            // 4..5  Length (UnitID + FC + DataN)
            // 6     UnitID
            // 7     FunctionCode
            // 8..9  param1
            // 10..11 param2
            // 12..13 param3
            // 14..15 param4
            // 16..17 DO (Digital Output)
            // 18..19 STATE
            
            // Extract DO and STATE values
            ushort doValue = pdu.Length > 18 ? ReadBE16(pdu.Slice(16, 2)) : (ushort)0;
            ushort stateValue = ReadBE16(pdu.Slice(18, 2));
            _logger?.LogDebug("DO value: 0x{DoValue:X4}, State value: 0x{StateValue:X4}", doValue, stateValue);

            // Determine device type and DO description based on destination IP
            bool isPbe = dstIp == "132.8.7.101";
            bool isSbe = dstIp == "132.8.7.102";
            bool isLocalhost = dstIp == "127.0.0.1";
            _logger?.LogDebug("Device type - PBE: {IsPbe}, SBE: {IsSbe}, Localhost: {IsLocalhost}", isPbe, isSbe, isLocalhost);
            
            IReadOnlyDictionary<ushort, string>? doMap = isPbe ? DO_PBE : (isSbe || isLocalhost) ? DO_SBE : null;
            
            string doDescription = doMap?.TryGetValue(doValue, out var doName) == true 
                ? doName 
                : $"0x{doValue:X4}";

            string stateDescription = STATE.TryGetValue(stateValue, out var stateName) 
                ? stateName 
                : $"0x{stateValue:X4}";

            _logger?.LogDebug("Parsed values - DO: {DoDescription}, State: {StateDescription}", doDescription, stateDescription);

            // Build entity (matching TypeScript SafetyDTO structure)
            var entity = new SafetyPacketEntity
            {
                Id = Guid.NewGuid(),
                Timestamp = DateTime.UtcNow,
                Type = isPbe, // true for PBE, false for SBE
                OpCode = doValue.ToString(),
                OpCodeDescription = doDescription,
                State = stateDescription
            };

            _logger?.LogInformation("Successfully parsed safety packet - DO: {DoDescription}, State: {StateDescription}, Device: {DeviceType}", 
                doDescription, stateDescription, isPbe ? "PBE" : isSbe ? "SBE" : "Unknown");
            
            return entity;
        }
        catch (Exception ex)
        {
            _logger?.LogError(ex, "Error parsing safety packet. Packet length: {Length} bytes, Raw data: {Data}", 
                rawPacket.Length, BitConverter.ToString(rawPacket.ToArray()).Replace("-", ""));
            return null;
        }
    }

    private static ushort ReadBE16(ReadOnlySpan<byte> s) => 
        BinaryPrimitives.ReadUInt16BigEndian(s);

    private static string ToIPv4(ReadOnlySpan<byte> s) =>
        $"{s[0]}.{s[1]}.{s[2]}.{s[3]}";
}
