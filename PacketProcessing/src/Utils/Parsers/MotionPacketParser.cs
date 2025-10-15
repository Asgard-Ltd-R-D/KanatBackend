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

    // Cached opcode strings to avoid allocations
    private static readonly Dictionary<ushort, string> OpCodeStrings = new();
    private static readonly object _opCodeLock = new();
    
    // OpCode -> Description map (from your Lua e_opcode)
    private static readonly Dictionary<ushort, string> OpCodeDescriptions = new()
    {
        //Motion Commands
        {0x0101,"MOT_MerRegister"},
        {0x0102,"MOT_DerRegister"},
        {0x0103,"MOT_SrhRegister"},
        {0x0104,"MOT_SrlRegister"},
        {0x0105,"MOT_MsrRegister"},
        {0x0106,"MOT_GetMotorCurrent"},
        {0x0107,"MOT_GetMotorVoltage"},
        {0x0108,"MOT_GetMotorPosition"},
        {0x0109,"MOT_GetLoadPosition"},
        {0x010A,"MOT_GetMotorSpeed"},
        {0x010C,"MOT_GetNegSWLS"},
        {0x010D,"MOT_GetPosSWLS"},
        {0x0110,"MOT_IsActiveSWLS"},
        {0x014F,"MOT_GetShortPath"},
        {0x012E,"MOT_GetMaxCurrent"},
        {0x0130,"MOT_SetAcceleration"},
        {0x0131,"MOT_SetSpeed"},
        {0x0132,"MOT_SendPosition"},
        {0x0133,"MOT_SetActualPosition"},
        {0x0134,"MOT_Update"},
        {0x0135,"MOT_Homing"},
        {0x0136,"MOT_SetNegSWLS"},
        {0x0137,"MOT_SetPosSWLS"},
        {0x0146,"MOT_ActivateSWLS"},
        {0x0138,"MOT_SetPositionRelative"},
        {0x0139,"MOT_SetPositionAbsolute"},
        {0x013A,"MOT_SetSpeedMode"},
        {0x013B,"MOT_SetPositionMode"},
        {0x013C,"MOT_AxisOn"},
        {0x013D,"MOT_AxisOff"},
        {0x013E,"MOT_AxisReset"},
        {0x013F,"MOT_SetTum"},
        {0x0143,"MOT_ResetFaults"},
        {0x014E,"MOT_SetShortPath"},
        {0x0165,"MOT_SaveMotorSetting"},
        {0x0166,"MOT_SetMaxCurrent"},
        {0x0144,"MOT_SetMotionComplete"},

        //Scan Commands
        {0x0400,"SCN_SetYawMin"},
        {0x0401,"SCN_SetYawMax"},
        {0x0402,"SCN_SetPitchMin"},
        {0x0403,"SCN_SetNumSteps"},
        {0x0404,"SCN_SetStepHeight"},
        {0x0405,"SCN_SetScanSpeed"},
        {0x0406,"SCN_SetShortPath"},
        {0x0407,"SCN_IsScanOn"},
        {0x0408,"SCN_StopScan"},
        {0x040C,"SCN_StartScanZigZag"},
        {0x040D,"SCN_StartScanSnake"},
        {0x040E,"SCN_StartScanSquare"},

        //Communication Commands
        {0x0700,"COM_Reboot"},
        {0x0702,"COM_Connect"},
        {0x0703,"COM_Disconnect"},
        {0x0704,"COM_IsConnected"},
        {0x0705,"COM_StartKeepAlive"},
        {0x0706,"COM_IsKeepAliveOn"},
        {0x0708,"COM_setKeepAliveTimeout"},
        {0x0709,"COM_getKeepAliveTimeout"},
        {0x071C,"COM_setKeepAliveCount"},
        {0x071D,"COM_getKeepAliveCount"},
        {0x0719,"COM_SetComType"},
        {0x0713,"COM_SysState"},

        //Stabilization Commands
        {0x0800,"STB_StabilizationOn"},
        {0x0801,"STB_StabilizationOff"},
        {0x0822,"STB_GetStabError"},
        {0x0839,"STB_SetStabMinAccel"},
        {0x083A,"STB_GetStabMinAccel"},
        {0x0D04,"STB_SetSpdKp"},
        {0x0D08,"STB_GetSpdKp"},
        {0x0D05,"STB_SetSpdKi"},
        {0x0D09,"STB_GetSpdKi"},
        {0x0D06,"STB_SetSpdKd"},
        {0x0D0A,"STB_GetSpdKd"},
        {0x0D16,"STB_SetPosKp"},
        {0x0D17,"STB_GetPosKp"},
        {0x0D18,"STB_SetPosKi"},
        {0x0D19,"STB_GetPosKi"},
        {0x0D1A,"STB_SetPosKd"},
        {0x0D1B,"STB_GetPosKd"},
        {0x082B,"STB_SetDistanceToTarget"},
        {0x082A,"STB_GetDistanceToTarget"},
        {0x0825,"STB_SetCentralAxes"},
        {0x0826,"STB_GetCentralAxes"},
        {0x0C76,"STB_SetRollCompensation"},
        {0x0C77,"STB_GetRollCompensation"},
        {0x084F,"STB_SetRebalanceOn"},
        {0x0850,"STB_GetRebalanceOn"},
        {0x0851,"STB_GetRebalanceStatus"},
        {0x0D07,"STB_SaveStabilizationCfg"},

        //Gimbal Commands
        {0x0FA0,"DG_SetSyncMode"},
        {0x0FA1,"DG_SetInnerMode"},
        {0x0FA2,"DG_IsSyncMode"},
        {0x0FA3,"DG_IsInnerMode"},
        {0x0FA5,"DG_GetPosDiff"},
        {0x0FA6,"DG_SetMaxDiff"},
        {0x0FA7,"DG_GetMaxDiff"},
        {0x0FA9,"DG_GoToCamera"},
        {0x0FAA,"DG_SetSyncSpd"},
        {0x0FAB,"DG_SetMainGimbal"},
        {0x0FAC,"DG_GetMainGimbal"},
        {0x0FB0,"DG_CTC"},
        {0x0FB1,"DG_GetCTCoffset"},
        {0x0FB2,"DG_ResetCTCoffset"},
        {0x0FB5,"DG_GetSyncSpd"},
        {0x0FB6,"DG_SetActiveWeapon"},
        {0x0FB7,"DG_GetActiveWeapon"},
        {0x0FBA,"DG_SetActiveCamera"},
        {0x0FBB,"DG_GetActiveCamera"},
        {0x0FB9,"DG_IsBoresightEn"},
        {0x0FBC,"DG_GetBoresightOffset"},
        {0x0FBD,"DG_SetBallisticOffset"},
        {0x0FBE,"DG_GetBallisticOffset"},
        {0x0FBF,"DG_GetSafetyStatus"},
        {0x0FC0,"DG_GetLoadStatus"},
        {0x0FC1,"DG_GetCapsnapIOStatus"},
        {0x0FC2,"DG_GetNumBullets"},
        {0x0FC3,"DG_ResetNumBullets"},
        {0x0FC4,"DG_IsCapSnapReady"},

        //LRF Commands
        {0x0300,"LRF_SetRange"},
        {0x0301,"LRF_GetRange"},

        //Communication Commands
        {0x0C2D,"COM_GetPn"},
        {0x0C2F,"COM_GetSn"},
        {0x0C4A,"COM_GetFw"},
        {0x0C4C,"COM_GetHw"},

        //Error Commands
        {0x0E01,"ERR_CaptureSystemRegister"},
        {0x0E02,"ERR_ClearErrors"},
        {0x0E03,"ERR_GetDriverErrorString"},
        {0x0E04,"ERR_GetSystemErrorString"},
        {0x0E05,"ERR_GetLoadImuErrorString"},
        {0x0E06,"ERR_GetBaseImuErrorString"},
        {0x0E07,"ERR_GetGpsComErrorString"},
        {0x0E08,"ERR_GetGpsPosString"},
        {0x0E09,"ERR_GetGpsHeadErrorString"},
        {0x0E0A,"ERR_GetProtocolErrorString"},
        {0x0E0D,"ERR_GetAbsEncComErrorString"},
        {0x0E0E,"ERR_GetAbsEncCRCErrorString"},
        {0x0E0F,"ERR_GetBodyImuErrorString"},
        {0x0E10,"ERR_GetHomingErrorString"},
        {0x0E12,"ERR_OperationRegister"},

        //IP Commands
        {0x070A,"IP_SetControllerIP"},
        {0x070D,"IP_GetControllerIP"},
        {0x070B,"IP_SetControllerPort"},
        {0x070E,"IP_GetControllerPort"},
        {0x071A,"IP_SetControllerSubnetMask"},

        {0x0710,"IP_SaveIP"},
    };
    private const string REPORT_IP = "132.8.7.125";

    /// <summary>
    /// Parses raw packet data into a MotionPacketEntity
    /// [0..1]=StartByte (u16), [2]=Length (u8), [3]=GroupID (u8), [4]=AxisID (u8),
    /// [5..6]=OPCODE (u16, big-endian as in Wireshark default), [7..7+N-1]=DATA (N = Length-4),
    /// </summary>
    /// <param name="rawPacket">Raw packet bytes</param>
    /// <returns>Parsed MotionPacketEntity or null if parsing fails</returns>
    public static MotionPacketEntity? Parse(ReadOnlySpan<byte> rawPacket)
    {
        try
        {
            // --- Basic length sanity check ---
            if (rawPacket.Length < 62) return null; // too small to contain motion payload

            // --- Detect IPv4 header (with Ethernet prefix if present) ---
            int ipStart = (rawPacket.Length >= 14 && ReadBE16(rawPacket.Slice(12, 2)) == 0x0800) ? 14 : 0;
            if (rawPacket.Length < ipStart + 20 || (rawPacket[ipStart] >> 4) != 4) return null;

            int ihl = (rawPacket[ipStart] & 0x0F) * 4;
            if (ihl < 20 || rawPacket.Length < ipStart + ihl) return null;

            // --- Protocol check (expect TCP = 6) ---
            if (rawPacket[ipStart + 9] != 6) return null;

            // --- Extract Source IP (bytes 12–15 of IP header) ---
            var srcIp = $"{rawPacket[ipStart + 12]}.{rawPacket[ipStart + 13]}.{rawPacket[ipStart + 14]}.{rawPacket[ipStart + 15]}";

            bool isReport = srcIp == REPORT_IP;

            // Axis + Opcode
            byte axis = rawPacket[58];
            ushort opCode = ReadBE16(rawPacket.Slice(59, 2));

            string opDesc = OpCodeDescriptions.TryGetValue(opCode, out var desc) ? desc : "Unknown";

            float? floatValue = null;

            // Extract float only if report packet
            if (isReport)
            {
                bool isLrf = opDesc.StartsWith("LRF_", StringComparison.OrdinalIgnoreCase);

                if (isLrf && rawPacket.Length >= 63)
                {
                    // 16-bit IEEE754 half float → float32
                    ushort half = BinaryPrimitives.ReadUInt16LittleEndian(rawPacket.Slice(61, 2));
                    floatValue = HalfToSingle(half);
                }
                else if (rawPacket.Length >= 65)
                {
                    // 32-bit float little-endian
                    uint le = BinaryPrimitives.ReadUInt32LittleEndian(rawPacket.Slice(61, 4));
                    floatValue = BitConverter.Int32BitsToSingle(unchecked((int)le));
                }
            }

            return new MotionPacketEntity
            {
                Id = Guid.NewGuid(),
                Timestamp = DateTime.UtcNow,
                Axis = axis,
                OpCode = $"0x{opCode:X4}",
                OpCodeDescription = opDesc,
                FloatValue = floatValue,
                IsCmd = !isReport
            };
        }
        catch (Exception ex)
        {
            if (_logger?.IsEnabled(LogLevel.Debug) ?? false)
                _logger.LogDebug(ex, "Error parsing motion packet. Length: {Length} bytes", rawPacket.Length);
            return null;
        }
    }

    // Convert IEEE-754 16-bit half float to single float
    private static float HalfToSingle(ushort half)
    {
        uint sign = (uint)(half >> 15) & 0x00000001;
        uint exp = (uint)(half >> 10) & 0x0000001F;
        uint mant = (uint)half & 0x000003FF;

        if (exp == 0)
        {
            if (mant == 0)
                return BitConverter.Int32BitsToSingle((int)(sign << 31));
            else
            {
                while ((mant & 0x00000400) == 0)
                {
                    mant <<= 1;
                    exp--;
                }
                exp++;
                mant &= ~0x00000400U;
            }
        }
        else if (exp == 31)
        {
            if (mant == 0)
                return BitConverter.Int32BitsToSingle((int)((sign << 31) | 0x7F800000));
            else
                return BitConverter.Int32BitsToSingle((int)((sign << 31) | 0x7F800000 | (mant << 13)));
        }

        exp = exp + (127 - 15);
        mant = mant << 13;
        uint bits = (sign << 31) | (exp << 23) | mant;
        return BitConverter.Int32BitsToSingle((int)bits);
    }

    private static ushort ReadBE16(ReadOnlySpan<byte> s) =>
        BinaryPrimitives.ReadUInt16BigEndian(s);
}
