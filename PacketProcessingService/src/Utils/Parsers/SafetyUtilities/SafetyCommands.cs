using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Utils.Parsers.SafetyUtilities;

public static class SafetyCommands
{
    public static readonly Dictionary<(int, SafetyTypes), SafetyRecord> SafetyRecords = new()
    {
        // PBE DO maps
        [ (0x0010, SafetyTypes.PBE) ] =  new SafetyRecord("1"),
        [ (0x0027, SafetyTypes.PBE) ] =  new SafetyRecord("DO3_FIRE1"),
        [ (0x0012, SafetyTypes.PBE) ] =  new SafetyRecord("DO2_MOTION"),
        [ (0x0014, SafetyTypes.PBE) ] =  new SafetyRecord("DO4_LED_FIRE_EN"),

        // SBE DO maps
        [ (0x0010, SafetyTypes.SBE) ] =  new SafetyRecord("DO0_RLD"),
        [ (0x0011, SafetyTypes.SBE) ] =  new SafetyRecord("DO1_RLD_SFTY"),
        [ (0x0012, SafetyTypes.SBE) ] =  new SafetyRecord("DO2_PWR"),
        [ (0x0028, SafetyTypes.SBE) ] =  new SafetyRecord("DO4_FIRE2"),
        [ (0x0015, SafetyTypes.SBE) ] =  new SafetyRecord("X5"),

        // State values are the same for both PBE and SBE, so we can just use one set of records for both types
        [ (0x0000, SafetyTypes.STATE) ] =  new SafetyRecord("OFF"),
        [ (0xFF00, SafetyTypes.STATE) ] =  new SafetyRecord("ON"),
        [ (0x0001, SafetyTypes.STATE) ] =  new SafetyRecord("PULSE"),
        [ (0x0003, SafetyTypes.STATE) ] =  new SafetyRecord("BURST")
    };
}
