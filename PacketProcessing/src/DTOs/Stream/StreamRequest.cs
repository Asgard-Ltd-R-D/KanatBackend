using System.Text;
using System.Text.Json;
using PacketProcessing.Entities;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.DTOs.Stream;

/// <summary>
/// Stream request for packet transmission
/// Real-time: Only DataPipe is set
/// Playback: All fields are set for detailed filtering
/// </summary>
public sealed class StreamRequest
{
    /// <summary>
    /// Data pipe type (always required)
    /// </summary>
    public required DataPipes DataPipe { get; init; }
    
    /// <summary>
    /// Is this a playback request? (derived from whether optional fields are set)
    /// </summary>
    public bool IsPlayback => StartTimestamp.HasValue || EndTimestamp.HasValue || IsCmd.HasValue;
    
    // Optional fields for playback filtering
    public DateTime? StartTimestamp { get; init; }
    public DateTime? EndTimestamp { get; init; }
    public int IntervalMs { get; init; } = 1000;

    public string? MethodName { get; init; }
    public bool? IsCmd { get; init; }
    public IReadOnlyDictionary<string, JsonElement>? Data { get; init; }

    private string? _subscriptionKey;
    public string SubscriptionKey => _subscriptionKey ??= BuildSubscriptionKey();

    public string BuildSubscriptionKey()
    {
        var sb = new StringBuilder();
        
        sb.Append("pipe=").Append(DataPipe).Append('|')
          .Append("method=").Append(MethodName);

        // Add optional fields to key if they are set
        if (IsCmd.HasValue)
            sb.Append("|cmd=").Append(IsCmd.Value);
            
        if (StartTimestamp.HasValue)
            sb.Append("|start=").Append(StartTimestamp.Value.Ticks);
            
        if (EndTimestamp.HasValue)
            sb.Append("|end=").Append(EndTimestamp.Value.Ticks);
        
        if (Data is { Count: > 0 })
        {
            foreach (var kv in Data.OrderBy(k => k.Key, StringComparer.Ordinal))
            {
                sb.Append('|')
                  .Append(kv.Key)
                  .Append('=')
                  .Append(CanonicalizeJson(kv.Value));
            }
        }

        return sb.ToString();
    }

    private static string CanonicalizeJson(JsonElement el)
    {
        switch (el.ValueKind)
        {
            case JsonValueKind.Object:
            {
                var parts = el.EnumerateObject()
                              .OrderBy(p => p.Name, StringComparer.Ordinal)
                              .Select(p => $"{JsonSerializer.Serialize(p.Name)}:{CanonicalizeJson(p.Value)}");
                return "{" + string.Join(",", parts) + "}";
            }
            case JsonValueKind.Array:
            {
                var parts = el.EnumerateArray().Select(CanonicalizeJson);
                return "[" + string.Join(",", parts) + "]";
            }
            case JsonValueKind.String:
                return JsonSerializer.Serialize(el.GetString());
            case JsonValueKind.Number:
            case JsonValueKind.True:
            case JsonValueKind.False:
            case JsonValueKind.Null:
                return el.GetRawText();
            default:
                return el.GetRawText();
        }
    }
    
    /// <summary>
    /// Check if a packet matches this stream request
    /// Real-time: Only checks DataPipe
    /// Playback: Checks all set fields (DataPipe, IsCmd, timestamp range, etc.)
    /// </summary>
    public bool MatchesPacket(BasePacketEntity packet)
    {
        // Always check DataPipe type
        var packetType = packet switch
        {
            MotionPacketEntity => DataPipes.Motion,
            OnVIFPacketEntity => DataPipes.Onvif,
            SafetyPacketEntity => DataPipes.Safety,
            _ => (DataPipes?)null
        };

        if (packetType != DataPipe)
            return false;

        // If IsCmd is set, check it
        if (IsCmd.HasValue && packet.IsCmd != IsCmd.Value)
            return false;

        // If timestamp range is set, check it
        if (StartTimestamp.HasValue && packet.Timestamp < StartTimestamp.Value)
            return false;
            
        if (EndTimestamp.HasValue && packet.Timestamp > EndTimestamp.Value)
            return false;

        // Additional custom data checks can be added here if needed
        return true;
    }
}
