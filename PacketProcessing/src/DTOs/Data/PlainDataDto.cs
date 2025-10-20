using System.Text.Json.Serialization;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.DTOs.Data;

public class PlainDataDto
{
    public DateTime Timestamp { get; set; } = DateTime.UtcNow;
    public double Value { get; set; } = 0.0d;
    
    [property: JsonConverter(typeof(JsonStringEnumConverter))]
    public DataPipes DataPipe { get; set; }
    
    public string MethodName { get; set; } = string.Empty;
}