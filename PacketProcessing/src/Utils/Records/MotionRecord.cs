using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Utils.Records;

/// <summary>
/// Record for motion packets
/// </summary>
/// <param name="Type">The type of the motion packet</param>
/// <param name="OpCodeDescription">The description of the motion packet</param>
/// <param name="Value">The value of the motion packet</param>
public record MotionRecord(MotionValueTypes ValueType,string OpCodeDescription,float Value);
