using System.Text.Json.Serialization;

namespace PacketProcessing.Models;

public class PacketData
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public DateTime Timestamp { get; set; } = DateTime.UtcNow;
    public string SourceIp { get; set; } = string.Empty;
    public string DestinationIp { get; set; } = string.Empty;
    public int SourcePort { get; set; }
    public int DestinationPort { get; set; }
    public int Length { get; set; }
    public string Protocol { get; set; } = string.Empty;
    public byte[] Payload { get; set; } = Array.Empty<byte>();
    public string DeviceName { get; set; } = string.Empty;
    
    [JsonIgnore]
    public string PayloadHex => Convert.ToHexString(Payload);
    
    [JsonIgnore]
    public string PayloadAscii => System.Text.Encoding.ASCII.GetString(Payload);
}
