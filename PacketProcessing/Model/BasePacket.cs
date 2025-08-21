namespace PacketProcessing.Model;

public abstract class BasePacket
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public ulong Timestamp { get; init; }             // e.g., microseconds since epoch
    public string SourceIp { get; init; } = "";
    public string DestinationIp { get; init; } = "";
    public int SourcePort { get; init; }
    public int DestinationPort { get; init; }
    public int Length { get; init; }
    public string Protocol { get; init; } = "";
    public string DeviceName { get; init; } = "";

    // Raw payload, zero-copy
    public ReadOnlyMemory<byte> Payload { get; init; } = ReadOnlyMemory<byte>.Empty;
}