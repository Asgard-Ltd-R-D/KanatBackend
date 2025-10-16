namespace PacketProcessing.Utils.Enums;

/// <summary>
/// Value types for motion commands, each one stores the number of bits.
/// </summary>
public enum ValueTypes
{
    None = 0,             // 0 bits
    Bool = 1,             // 1 byte 0/1
    UInt8 = 8,            // 1 byte
    UInt16BE = 16,        // 2 bytes big-endian
    UInt32BE = 32,        // 4 bytes big-endian
    Float32BE = 32,       // 4 bytes IEEE754 big-endian
}
