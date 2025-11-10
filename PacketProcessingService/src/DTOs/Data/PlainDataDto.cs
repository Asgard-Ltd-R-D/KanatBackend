using System.Text.Json.Serialization;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.DTOs.Data;

public class PlainDataDto
{
    public string SubscriptionKey { get; set; } = string.Empty;
    public long Timestamp { get; set; } = new DateTimeOffset(DateTime.UtcNow).ToUnixTimeMilliseconds();
    public double Value { get; set; } = 0.0d;
}