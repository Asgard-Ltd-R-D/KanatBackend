using System.Text;
using System.Text.Json.Serialization;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.DTOs.Stream;

/// <summary>
/// Stream request for packet transmission
/// Real-time: Only DataPipe is set
/// Playback: All fields are set for detailed filtering
/// </summary>
public sealed class StreamRequestDto
{
    /// <summary>
    /// Data pipe type (always required)
    /// </summary>
    [JsonConverter(typeof(JsonStringEnumConverter<DataPipes>))]
    public required DataPipes DataPipe { get; init; }
    /// <summary>
    /// Description of the method hex code/ opcode (e.g. "MOT_GetMotorCurrent", "FOV_REQ", "DO3_FIRE1", "LRF_STS", "MOT_GetMotorSpeed", "LRF_REQ", "DG_SetSyncMode", "DG_SetInnerMode", "DG_IsSyncMode", "DG_IsInnerMode", "DG_GetPosDiff", "DG_CTC", "DG_GetCTCoffset", "DG_IsBoresightEn", "DG_GetBoresightOffset", "DG_SetBallisticOffset")
    /// </summary>
    public required string Description { get; init; }
    /// <summary>
    /// Whether the method is a CMD or a RPT
    /// </summary>
    public bool? IsCmd { get; init; } = false; // The base configuration is false which means it will send RPT, otherwise it will send CMD

    /// <summary>
    /// Axis of the motion packet specifically to MOT_* commands, for other data pipes and other motion commands, this will be ignored.
    /// </summary>
    public int? Axis { get; init; } = 0; // If zero it will be ignored

    /// <summary>
    /// Optional sampling interval in milliseconds. If provided on registration, the server will set the interval for this subscription key after successful registration.
    /// If provided to SetTimeInterval, values: 0 disables sampling, >0 sets the interval, <0 is invalid.
    /// </summary>
    public int? IntervalMs { get; init; }

    /// <summary>
    /// Subscription key for the stream request, this is used to identify the stream request and to filter the packets.
    /// </summary>
    private string? _subscriptionKey;

    /// <summary>
    /// Subscription key for the stream request, this is used to identify the stream request and to filter the packets.
    /// </summary>
    /// <returns>The subscription key</returns>
    public string SubscriptionKey => _subscriptionKey ??= BuildSubscriptionKey();

    /// <summary>
    /// Build the subscription key for the stream request, this is used to identify the stream request and to filter the packets.
    /// For none motion packets, the axis is not included in the subscription key, and the key will set as follows: {DataPipe}|{Description}|{IsCmd}
    /// For motion packets, the axis is included in the subscription key, and the key will set as follows: {DataPipe}|{Description}|{IsCmd}|{Axis}
    /// 
    /// Note: The subscription key is lowercased before returning.
    /// </summary>
    /// <returns>The subscription key</returns>
    public string BuildSubscriptionKey()
    {
        var sb = new StringBuilder();
        sb.Append(DataPipe).Append('|')
        .Append(Description)
        .Append('|')
        .Append(IsCmd.HasValue ? IsCmd.Value.ToString() : "false");
        
        // Only Motion packets include axis in subscription key
        if (DataPipe == DataPipes.Motion)
        {
            sb.Append('|').Append(Axis.HasValue ? Axis.Value.ToString() : "");
        }

        _subscriptionKey = sb.ToString().ToLower(); // Lowercased before returning, and setting the private member
        return _subscriptionKey;
    }
}
