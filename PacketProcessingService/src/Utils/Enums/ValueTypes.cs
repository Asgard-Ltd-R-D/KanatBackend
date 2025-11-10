namespace PacketProcessing.Utils.Enums;

/// <summary>
/// Value types for motion commands, each one stores the number of bits.
/// </summary>
public enum ValueTypes
{
    None,             // 0 bits
    UInt8,            // 1 byte
    UInt16BE,        // 2 bytes big-endian
    UInt32BE,        // 4 bytes big-endian
    Float32BE,       // 4 bytes IEEE754 big-endian
}
