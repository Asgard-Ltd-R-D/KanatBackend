using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Utils.Parsers.MotionUtilities;

public static class MotionCommands
{
    public static readonly Dictionary<ushort, MotionRecord> MotionRecords = new()
    {
        // Get data commands
        { 0x0106, new MotionRecord("MOT_GetMotorCurrent", ValueTypes.None, ValueTypes.Float32BE) },
        { 0x0107, new MotionRecord("MOT_GetMotorVoltage", ValueTypes.None, ValueTypes.Float32BE) },
        { 0x0108, new MotionRecord("MOT_GetMotorPosition", ValueTypes.None, ValueTypes.Float32BE) },
        { 0x0109, new MotionRecord("MOT_GetLoadPosition", ValueTypes.None, ValueTypes.Float32BE) },
        { 0x010A, new MotionRecord("MOT_GetMotorSpeed", ValueTypes.None, ValueTypes.Float32BE) },

        // LRF commands
        { 0x0300, new MotionRecord("LRF_SetRange", ValueTypes.Float32BE, ValueTypes.None) },
        { 0x0301, new MotionRecord("LRF_GetRange", ValueTypes.None, ValueTypes.Float32BE) },

        // Dual Gimbals commands
        { 0x0FA0, new MotionRecord("DG_SetSyncMode", ValueTypes.UInt8, ValueTypes.None) },
        { 0x0FA1, new MotionRecord("DG_SetInnerMode", ValueTypes.UInt8, ValueTypes.None) },
        { 0x0FA2, new MotionRecord("DG_IsSyncMode", ValueTypes.None, ValueTypes.UInt8) },
        { 0x0FA3, new MotionRecord("DG_IsInnerMode", ValueTypes.None, ValueTypes.UInt8) },
        { 0x0FA5, new MotionRecord("DG_GetPosDiff", ValueTypes.None, ValueTypes.Float32BE) },
        { 0x0FB0, new MotionRecord("DG_CTC", ValueTypes.None, ValueTypes.None) },
        { 0x0FB1, new MotionRecord("DG_GetCTCoffset", ValueTypes.None, ValueTypes.Float32BE) },
        { 0x0FB9, new MotionRecord("DG_IsBoresightEn", ValueTypes.None, ValueTypes.UInt8) },
        { 0x0FBC, new MotionRecord("DG_GetBoresightOffset", ValueTypes.None, ValueTypes.Float32BE) },
        { 0x0FBD, new MotionRecord("DG_SetBallisticOffset", ValueTypes.Float32BE, ValueTypes.None) },
        { 0x0FBE, new MotionRecord("DG_GetBallisticOffset", ValueTypes.None, ValueTypes.Float32BE) },
    };
}