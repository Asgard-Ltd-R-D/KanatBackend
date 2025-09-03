using PacketProcessing.Entities.Packet;
using System.Buffers.Binary;
using System.Collections.Generic;

namespace PacketProcessing.Utils;

/// <summary>
/// Protocol types for packet parsing
/// </summary>
public enum Protocol
{
    TCP,
    UDP,
    HTTP
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
                // ---- OPCODE map (subset, extend as needed to match your Lua table) ----
        private static readonly IReadOnlyDictionary<ushort, string> OPCODES = new Dictionary<ushort, string>
        {
            { 0x0101, "MOT_MerRegister" },
            { 0x0102, "MOT_DerRegister" },
            { 0x0103, "MOT_SrhRegister" },
            { 0x0104, "MOT_SrlRegister" },
            { 0x0105, "MOT_MsrRegister" },
            { 0x0106, "MOT_GetMotorCurrent" },
            { 0x0107, "MOT_GetMotorVoltage" },
            { 0x0108, "MOT_GetMotorPosition" },
            { 0x0109, "MOT_GetLoadPosition" },
            { 0x010A, "MOT_GetMotorSpeed" },
            { 0x010C, "MOT_GetNegSWLS" },
            { 0x010D, "MOT_GetPosSWLS" },
            { 0x0110, "MOT_IsActiveSWLS" },
            { 0x014F, "MOT_GetShortPath" },
            { 0x012E, "MOT_GetMaxCurrent" },
            { 0x0130, "MOT_SetAcceleration" },
            { 0x0131, "MOT_SetSpeed" },
            { 0x0132, "MOT_SendPosition" },
            { 0x0133, "MOT_SetActualPosition" },
            { 0x0134, "MOT_Update" },
            { 0x0135, "MOT_Homing" },
            { 0x0136, "MOT_SetNegSWLS" },
            { 0x0137, "MOT_SetPosSWLS" },
            { 0x0146, "MOT_ActivateSWLS" },
            { 0x0138, "MOT_SetPositionRelative" },
            { 0x0139, "MOT_SetPositionAbsolute" },
            { 0x013A, "MOT_SetSpeedMode" },
            { 0x013B, "MOT_SetPositionMode" },
            { 0x013C, "MOT_AxisOn" },
            { 0x013D, "MOT_AxisOff" },
            { 0x013E, "MOT_AxisReset" },
            { 0x013F, "MOT_SetTum" },
            { 0x0143, "MOT_ResetFaults" },
            { 0x014E, "MOT_SetShortPath" },
            { 0x0165, "MOT_SaveMotorSetting" },
            { 0x0166, "MOT_SetMaxCurrent" },
            { 0x0144, "MOT_SetMotionComplete" },

            // SCN (scan)
            { 0x0400, "SCN_SetYawMin" },
            { 0x0401, "SCN_SetYawMax" },
            { 0x0402, "SCN_SetPitchMin" },
            { 0x0403, "SCN_SetNumSteps" },
            { 0x0404, "SCN_SetStepHeight" },
            { 0x0405, "SCN_SetScanSpeed" },
            { 0x0406, "SCN_SetShortPath" },
            { 0x0407, "SCN_IsScanOn" },
            { 0x0408, "SCN_StopScan" },
            { 0x040C, "SCN_StartScanZigZag" },
            { 0x040D, "SCN_StartScanSnake" },
            { 0x040E, "SCN_StartScanSquare" },

            // COM
            { 0x0700, "COM_Reboot" },
            { 0x0702, "COM_Connect" },
            { 0x0703, "COM_Disconnect" },
            { 0x0704, "COM_IsConnected" },
            { 0x0705, "COM_StartKeepAlive" },
            { 0x0706, "COM_IsKeepAliveOn" },
            { 0x0708, "COM_setKeepAliveTimeout" },
            { 0x0709, "COM_getKeepAliveTimeout" },
            { 0x071C, "COM_setKeepAliveCount" },
            { 0x071D, "COM_getKeepAliveCount" },
            { 0x0719, "COM_SetComType" },
            { 0x0713, "COM_SysState" },

            // STB (stabilization) – add the rest as needed
            { 0x0800, "STB_StabilizationOn" },
            { 0x0801, "STB_StabilizationOff" },
        };

        /// <summary>
        /// Parses raw packet data into a MotionPacketEntity
        /// </summary>
        /// <param name="rawPacket">Raw packet bytes</param>
        /// <returns>Parsed MotionPacketEntity or null if parsing fails</returns>
        internal static MotionPacketEntity ParseMotionPacket(ReadOnlySpan<byte> rawPacket)
        {
            // ---- Ethernet ----
            if (rawPacket.Length < 14) return null!;
            int offset;

            // EtherType (with VLAN/QinQ support)
            ushort ethType = ReadBE16(rawPacket.Slice(12, 2));
            offset = 14;

            // VLAN (0x8100) / QinQ (0x88A8)
            if (ethType == 0x8100 || ethType == 0x88A8)
            {
                if (rawPacket.Length < offset + 4) return null!;
                ethType = ReadBE16(rawPacket.Slice(offset + 2, 2));
                offset += 4;
            }

            // ---- IPv4 only (0x0800) ----
            if (ethType != 0x0800) return null!;
            if (rawPacket.Length < offset + 20) return null!;

            // IPv4 header
            int ipStart = offset;
            byte verIhl = rawPacket[ipStart];
            int version = verIhl >> 4;
            if (version != 4) return null!;

            // IP header length
            int ihlBytes = (verIhl & 0x0F) * 4;
            if (ihlBytes < 20) return null!;
            if (rawPacket.Length < ipStart + ihlBytes) return null!;

            // Protocol
            byte protocol = rawPacket[ipStart + 9];
            if (protocol != 6) return null!; // TCP

            // Source/Dest IPs
            string dstIp = ToIPv4(rawPacket.Slice(ipStart + 16, 4));

            // ---- TCP ----
            int tcpStart = ipStart + ihlBytes;
            if (rawPacket.Length < tcpStart + 20) return null!;
            
            ushort srcPort = ReadBE16(rawPacket.Slice(tcpStart + 0, 2));
            ushort dstPort = ReadBE16(rawPacket.Slice(tcpStart + 2, 2));
            byte dataOffsetReservedFlags = rawPacket[tcpStart + 12];
            int tcpHdrLen = ((dataOffsetReservedFlags >> 4) & 0x0F) * 4;
            if (tcpHdrLen < 20) return null!;
            if (rawPacket.Length < tcpStart + tcpHdrLen) return null!;

            int pduStart = tcpStart + tcpHdrLen;
            if (pduStart >= rawPacket.Length) return null!;
            var pdu = rawPacket[pduStart..];

            // We care only about port 4949 (either src or dst), same as Lua dissector registration
            if (srcPort != 4949 && dstPort != 4949) return null!;

            // ---- CapTrack PDU ----
            // Layout per Lua:
            // 0..1  StartByte (u16) [endian not enforced for semantics – just read bytes]
            // 2     Length (u8)
            // 3     GroupID (u8)
            // 4     AxisID (u8)
            // 5..6  OPCODE (u16)   [Lua reads with :le_uint() => little-endian]
            // 7..(7+DATA-1) DATA   [DATA length = Length - 4]
            // last 1 byte: CS
            if (pdu.Length < 8) return null!; // minimal header (through OPCODE)

            ushort startByte = ReadBE16(pdu[..2]); // presentation only
            byte length = pdu[2];
            byte groupId = pdu[3];
            byte axisId = pdu[4];
            ushort opcode = ReadLE16(pdu.Slice(5, 2)); // LE per Lua

            int dataLen = length - 4; // Length covers GroupID, AxisID, OPCODE(2)
            int dataOffset = 7;
            if (dataLen < 0) return null!;
            if (pdu.Length < dataOffset + dataLen + 1) return null!; // +1 for CS

            ReadOnlySpan<byte> data = dataLen > 0 ? pdu.Slice(dataOffset, dataLen) : [];
            byte cs = pdu[dataOffset + dataLen]; // trailing checksum byte 

            // Convert DATA into floats if multiple of 4, little-endian
            List<float>? floats = null;
            if (dataLen > 0 && (dataLen % 4) == 0)
            {
                floats = new List<float>(dataLen / 4);
                for (int i = 0; i < dataLen; i += 4)
                {
                    uint raw = ReadLE32(data.Slice(i, 4));
                    floats.Add(UintToFloat(raw));
                }
            }

            string opcodeText = OPCODES.TryGetValue(opcode, out var name) ? name : $"0x{opcode:X4}";

            // Build entity
            return new MotionPacketEntity
            {
                Id = Guid.NewGuid(),
                Timestamp = DateTime.UtcNow,
                Type = true, 
                Axis = axisId,
                OpCode = $"0x{opcode:X4}",
                OpCodeDescription = opcodeText,
                FloatValue = floats is { Count: > 0 } ? floats[0] : null
            };
        }
    }

    /// <summary>
    /// UDP parser for safety packets
    /// </summary>
    public static class UdpParser
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
        internal static SafetyPacketEntity ParseSafetyPacket(ReadOnlySpan<byte> rawPacket)
        {
            // ---- Ethernet ----
            if (rawPacket.Length < 14) return null!;
            int offset;

            // EtherType (with VLAN/QinQ handling)
            ushort ethType = ReadBE16(rawPacket[12..]);
            offset = 14;

            // VLAN (0x8100) / QinQ (0x88A8)
            if (ethType == 0x8100 || ethType == 0x88A8)
            {
                if (rawPacket.Length < offset + 4) return null!;
                ethType = ReadBE16(rawPacket[(offset + 2)..]);
                offset += 4;
            }

            // ---- IPv4 only (0x0800) ----
            if (ethType != 0x0800) return null!;
            if (rawPacket.Length < offset + 20) return null!; // min IPv4 header

            var ipStart = offset;
            byte verIhl = rawPacket[ipStart];
            int version = verIhl >> 4;
            if (version != 4) return null!;

            int ihlBytes = (verIhl & 0x0F) * 4;
            if (ihlBytes < 20) return null!;
            if (rawPacket.Length < ipStart + ihlBytes) return null!;

            byte protocol = rawPacket[ipStart + 9];
            if (protocol != 17) return null!; // UDP

            // Source/Dest IPs
            var dstIpSpan = rawPacket.Slice(ipStart + 16, 4);
            string dstIp = ToIPv4(dstIpSpan);

            // ---- UDP ----
            int udpStart = ipStart + ihlBytes;
            if (rawPacket.Length < udpStart + 8) return null!;

            // UDP length check (optional but nice)
            ushort udpLen = ReadBE16(rawPacket[(udpStart + 4)..]);
            if (udpLen < 8) return null!;
            if (rawPacket.Length < udpStart + udpLen) return null!;

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
            if (pdu.Length < 20) return null!;

            // Extract DO/STATE codes (big-endian)
            ushort doCode = ReadBE16(pdu.Slice(16, 2));
            ushort stateCode = ReadBE16(pdu.Slice(18, 2));

            IReadOnlyDictionary<ushort, string>? doMap =
                dstIp == "132.8.7.101" ? DO_PBE :
                dstIp == "132.8.7.102" ? DO_SBE : null;
            
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
                Type = true,
                OpCode = doText,
                OpCodeDescription = doText,
                State = stateText
            };
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

    private static ushort ReadBE16(ReadOnlySpan<byte> s) => 
        BinaryPrimitives.ReadUInt16BigEndian(s);
    private static ushort ReadLE16(ReadOnlySpan<byte> s) => 
        BinaryPrimitives.ReadUInt16LittleEndian(s);
    private static uint ReadLE32(ReadOnlySpan<byte> s) => 
        BinaryPrimitives.ReadUInt32LittleEndian(s);

    private static string ToIPv4(ReadOnlySpan<byte> s) =>
        $"{s[0]}.{s[1]}.{s[2]}.{s[3]}";

    private static float UintToFloat(uint raw)
    {
        // reinterpret-cast via bytes
        Span<byte> b = stackalloc byte[4];
        BinaryPrimitives.WriteUInt32LittleEndian(b, raw);
        return BitConverter.ToSingle(b);
    }
}
