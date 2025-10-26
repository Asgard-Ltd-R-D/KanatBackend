using System.Text.Json.Serialization;
using PacketProcessing.Utils.Enums;

public class AckDto
{
    [JsonConverter(typeof(JsonStringEnumConverter<OperationType>))]
    public required OperationType OperationType { get; init; }
    public required bool Success { get; init; }
    public string? Message { get; init; }
}