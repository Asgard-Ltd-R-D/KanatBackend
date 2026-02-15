using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Utils.Parsers.SafetyUtilities;

/// <summary>
/// Record for safety packets
/// </summary>
/// <param name="Type">The type of the safety packet</param>
public record SafetyRecord(string OpCodeDescription);
