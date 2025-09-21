using PacketProcessing.Entities.Packet;
using System.Buffers.Binary;
using Microsoft.Extensions.Logging;

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
    public static string? MotionDeviceIp { get; set; } = null;
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
        { 0x0800, "STB_SetYawMin" },
        { 0x0801, "STB_SetYawMax" },
        { 0x0802, "STB_SetPitchMin" },
        { 0x0803, "STB_SetPitchMax" },
        { 0x0804, "STB_SetYawSpeed" },
        { 0x0805, "STB_SetPitchSpeed" },
        { 0x0806, "STB_SetYawAcceleration" },
        { 0x0807, "STB_SetPitchAcceleration" },
        { 0x0808, "STB_SetYawDeceleration" },
        { 0x0809, "STB_SetPitchDeceleration" },
        { 0x080A, "STB_SetYawJerk" },
        { 0x080B, "STB_SetPitchJerk" },
        { 0x080C, "STB_SetYawPosition" },
        { 0x080D, "STB_SetPitchPosition" },
        { 0x080E, "STB_SetYawHome" },
        { 0x080F, "STB_SetPitchHome" },
        { 0x0810, "STB_SetYawOffset" },
        { 0x0811, "STB_SetPitchOffset" },
        { 0x0812, "STB_SetYawGain" },
        { 0x0813, "STB_SetPitchGain" },
        { 0x0814, "STB_SetYawIntegral" },
        { 0x0815, "STB_SetPitchIntegral" },
        { 0x0816, "STB_SetYawDerivative" },
        { 0x0817, "STB_SetPitchDerivative" },
        { 0x0818, "STB_SetYawFeedForward" },
        { 0x0819, "STB_SetPitchFeedForward" },
        { 0x081A, "STB_SetYawDeadband" },
        { 0x081B, "STB_SetPitchDeadband" },
        { 0x081C, "STB_SetYawHysteresis" },
        { 0x081D, "STB_SetPitchHysteresis" },
        { 0x081E, "STB_SetYawSlewRate" },
        { 0x081F, "STB_SetPitchSlewRate" },
        { 0x0820, "STB_SetYawSlewAcceleration" },
        { 0x0821, "STB_SetPitchSlewAcceleration" },
        { 0x0822, "STB_SetYawSlewDeceleration" },
        { 0x0823, "STB_SetPitchSlewDeceleration" },
        { 0x0824, "STB_SetYawSlewJerk" },
        { 0x0825, "STB_SetPitchSlewJerk" },
        { 0x0826, "STB_SetYawSlewPosition" },
        { 0x0827, "STB_SetPitchSlewPosition" },
        { 0x0828, "STB_SetYawSlewHome" },
        { 0x0829, "STB_SetPitchSlewHome" },
        { 0x082A, "STB_SetYawSlewOffset" },
        { 0x082B, "STB_SetPitchSlewOffset" },
        { 0x082C, "STB_SetYawSlewGain" },
        { 0x082D, "STB_SetPitchSlewGain" },
        { 0x082E, "STB_SetYawSlewIntegral" },
        { 0x082F, "STB_SetPitchSlewIntegral" },
        { 0x0830, "STB_SetYawSlewDerivative" },
        { 0x0831, "STB_SetPitchSlewDerivative" },
        { 0x0832, "STB_SetYawSlewFeedForward" },
        { 0x0833, "STB_SetPitchSlewFeedForward" },
        { 0x0834, "STB_SetYawSlewDeadband" },
        { 0x0835, "STB_SetPitchSlewDeadband" },
        { 0x0836, "STB_SetYawSlewHysteresis" },
        { 0x0837, "STB_SetPitchSlewHysteresis" },
        { 0x0838, "STB_SetYawSlewSlewRate" },
        { 0x0839, "STB_SetPitchSlewSlewRate" },
        { 0x083A, "STB_SetYawSlewSlewAcceleration" },
        { 0x083B, "STB_SetPitchSlewSlewAcceleration" },
        { 0x083C, "STB_SetYawSlewSlewDeceleration" },
        { 0x083D, "STB_SetPitchSlewSlewDeceleration" },
        { 0x083E, "STB_SetYawSlewSlewJerk" },
        { 0x083F, "STB_SetPitchSlewSlewJerk" },
        { 0x0840, "STB_SetYawSlewSlewPosition" },
        { 0x0841, "STB_SetPitchSlewSlewPosition" },
        { 0x0842, "STB_SetYawSlewSlewHome" },
        { 0x0843, "STB_SetPitchSlewSlewHome" },
        { 0x0844, "STB_SetYawSlewSlewOffset" },
        { 0x0845, "STB_SetPitchSlewSlewOffset" },
        { 0x0846, "STB_SetYawSlewSlewGain" },
        { 0x0847, "STB_SetPitchSlewSlewGain" },
        { 0x0848, "STB_SetYawSlewSlewIntegral" },
        { 0x0849, "STB_SetPitchSlewSlewIntegral" },
        { 0x084A, "STB_SetYawSlewSlewDerivative" },
        { 0x084B, "STB_SetPitchSlewSlewDerivative" },
        { 0x084C, "STB_SetYawSlewSlewFeedForward" },
        { 0x084D, "STB_SetPitchSlewSlewFeedForward" },
        { 0x084E, "STB_SetYawSlewSlewDeadband" },
        { 0x084F, "STB_SetPitchSlewSlewDeadband" },
        { 0x0850, "STB_SetYawSlewSlewHysteresis" },
        { 0x0851, "STB_SetPitchSlewSlewHysteresis" }
    };

    /// <summary>
    /// Parses raw packet data into a MotionPacketEntity
    /// </summary>
    /// <param name="rawPacket">Raw packet bytes</param>
    /// <returns>Parsed MotionPacketEntity or null if parsing fails</returns>
    public static MotionPacketEntity? Parse(ReadOnlySpan<byte> rawPacket)
    {
        try
        {
            _logger?.LogDebug("Starting motion packet parsing. Packet length: {Length} bytes", rawPacket.Length);
            _logger?.LogDebug("Raw packet data: {Data}", BitConverter.ToString(rawPacket.ToArray()).Replace("-", ""));
            
            // ---- Ethernet ----
            if (rawPacket.Length < 14)
            {
                _logger?.LogWarning("Packet too short for motion parsing. Length: {Length} bytes, minimum required: 14", rawPacket.Length);
                return null;
            }
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
        if (protocol != 6) return null; // TCP

        // ---- TCP ----
        int tcpStart = ipStart + ihlBytes;
        if (rawPacket.Length < tcpStart + 20) return null;

        byte dataOffsetFlags = rawPacket[tcpStart + 12];
        int tcpHdrLen = ((dataOffsetFlags >> 4) & 0x0F) * 4;
        if (tcpHdrLen < 20) return null;
        if (rawPacket.Length < tcpStart + tcpHdrLen) return null;

        int pduStart = tcpStart + tcpHdrLen;
        if (pduStart >= rawPacket.Length) return null;
        var pdu = rawPacket[pduStart..];

        // Determine Type (RPT/CMD) similar to TS: RPT when srcIP == MotionDeviceIp
        string srcIp = ToIPv4(rawPacket.Slice(ipStart + 12, 4));
        bool isRpt = MotionDeviceIp is not null ? srcIp.Equals(MotionDeviceIp, StringComparison.OrdinalIgnoreCase) : true;

        // ---- CapTrack PDU ----
        if (pdu.Length < 8) return null;

        // Check for CapTrack protocol header
        ushort opcode;
        byte axisId;
        int dataStart;
        
        if (pdu.Length >= 2 && pdu[0] == 0xCA && pdu[1] == 0xFE)
        {
            // CapTrack protocol header present
            if (pdu.Length < 8) return null;
            byte length = pdu[2];
            byte groupId = pdu[3];
            axisId = pdu[4];
            dataStart = 5;
            
            // Extract opcode (big-endian for CapTrack, matches TS parser)
            opcode = ReadBE16(pdu[dataStart..(dataStart + 2)]);
            dataStart += 2;
        }
        else
        {
            // Direct PDU format (big-endian opcode)
            opcode = ReadBE16(pdu[0..2]);
            axisId = pdu[2];
            dataStart = 3;
        }

        // Extract floats (CapTrack uses big-endian 4-byte float like TS parser)
        var floats = new List<float>();
        for (int i = dataStart; i + 4 <= pdu.Length; i += 4)
        {
            floats.Add(ReadFloatBE(pdu.Slice(i, 4)));
        }

        string opcodeText = OPCODES.TryGetValue(opcode, out var name) ? name : $"0x{opcode:X4}";

        // Build entity
            var entity = new MotionPacketEntity
            {
                Id = Guid.NewGuid(),
                Timestamp = DateTime.UtcNow,
                Type = isRpt,
                Axis = axisId,
                OpCode = $"0x{opcode:X4}",
                OpCodeDescription = opcodeText,
                FloatValue = floats is { Count: > 0 } ? floats[0] : null
            };

            _logger?.LogInformation("Successfully parsed motion packet - Type: {Type}, Axis: {Axis}, OpCode: {OpCode}, Description: {Description}, FloatValue: {FloatValue}", 
                isRpt ? "RPT" : "CMD", axisId, $"0x{opcode:X4}", opcodeText, floats is { Count: > 0 } ? floats[0] : null);
            
            return entity;
        }
        catch (Exception ex)
        {
            _logger?.LogError(ex, "Error parsing motion packet. Packet length: {Length} bytes, Raw data: {Data}", 
                rawPacket.Length, BitConverter.ToString(rawPacket.ToArray()).Replace("-", ""));
            return null;
        }
    }

    private static ushort ReadBE16(ReadOnlySpan<byte> s) => 
        BinaryPrimitives.ReadUInt16BigEndian(s);
    
    private static ushort ReadLE16(ReadOnlySpan<byte> s) => 
        BinaryPrimitives.ReadUInt16LittleEndian(s);
    
    private static uint ReadLE32(ReadOnlySpan<byte> s) => 
        BinaryPrimitives.ReadUInt32LittleEndian(s);

    private static float ReadFloatBE(ReadOnlySpan<byte> s)
    {
        Span<byte> b = stackalloc byte[4];
        // reverse for system little-endian ToSingle
        b[0] = s[3];
        b[1] = s[2];
        b[2] = s[1];
        b[3] = s[0];
        return BitConverter.ToSingle(b);
    }

    private static string ToIPv4(ReadOnlySpan<byte> s) =>
        $"{s[0]}.{s[1]}.{s[2]}.{s[3]}";
}
