namespace PacketProcessing.Utils.Enums;

public enum MotionValueTypes
{
    Bool,             // 1 byte 0/1
    UInt8,            // 1 byte
    UInt16BE,         // 2 bytes big-endian
    UInt32BE,         // 4 bytes big-endian
    Float32BE         // 4 bytes IEEE754 big-endian
}
