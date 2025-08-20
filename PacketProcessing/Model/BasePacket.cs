namespace PacketProcessing.Model;

public abstract class BasePacket;
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public long Timestamp { get; set; } = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
    public string SourceIp { get; set; } = string.Empty;
    public string DestinationIp { get; set; } = string.Empty;
    public int SourcePort { get; set; }
    public int DestinationPort { get; set; }
    public int Length { get; set; }
    public string Protocol { get; set; } = string.Empty;
    public string DeviceName { get; set; } = string.Empty;
}