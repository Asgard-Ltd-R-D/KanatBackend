using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Collections.Concurrent;
using SharpPcap.LibPcap;

namespace PacketProcessing.Services.Networking;

/// <summary>
/// OnVIF packet capture service
/// Captures OnVIF packets and writes them to the OnVIF channel
/// </summary>
public class OnVIFCaptureService : BaseCaptureService<OnVIFPacketEntity>
{
    public OnVIFCaptureService(
        ILogger<OnVIFCaptureService> logger,
        IConfiguration configurationManager,
        ConcurrentDictionary<string, LibPcapLiveDevice> activeDevices)
        : base(logger, configurationManager, "OnVIFCapture", activeDevices)
    {
        // Set up packet parser and handler
        PacketParser = ParseOnVIFPacket;
        PacketHandler = HandleOnVIFPacket;
    }

    /// <summary>
    /// Parses raw packet data into an OnVIFPacketEntity
    /// </summary>
    private OnVIFPacketEntity ParseOnVIFPacket(ReadOnlyMemory<byte> payload)
    {
        try
        {
            var span = payload.Span;
            
            // Validate minimum packet size
            if (span.Length < 10) // Minimum size for JSON packet
            {
                _logger.LogWarning("OnVIF packet too short: {Length} bytes", span.Length);
                return null;
            }
            
            var packet = new OnVIFPacketEntity
            {
                Id = Guid.NewGuid(),
                Timestamp = DateTime.UtcNow,
                Type = false,
                Description = string.Empty,
                Zoom = 0.0f,
                Measurement = 0.0f
            };
            
            // Parse JSON payload using Utf8JsonReader
            var jsonReader = new System.Text.Json.Utf8JsonReader(span);
            
            if (jsonReader.Read() && jsonReader.TokenType == System.Text.Json.JsonTokenType.StartObject)
            {
                while (jsonReader.Read() && jsonReader.TokenType == System.Text.Json.JsonTokenType.PropertyName)
                {
                    var propertyName = jsonReader.GetString();
                    
                    if (!jsonReader.Read()) break;
                    
                    switch (propertyName?.ToLower())
                    {
                        case "type":
                            if (jsonReader.TokenType == System.Text.Json.JsonTokenType.True || 
                                jsonReader.TokenType == System.Text.Json.JsonTokenType.False)
                            {
                                packet.Type = jsonReader.GetBoolean();
                            }
                            break;
                            
                        case "description":
                            if (jsonReader.TokenType == System.Text.Json.JsonTokenType.String)
                            {
                                packet.Description = jsonReader.GetString() ?? string.Empty;
                            }
                            break;
                            
                        case "zoom":
                            if (jsonReader.TokenType == System.Text.Json.JsonTokenType.Number)
                            {
                                packet.Zoom = jsonReader.GetSingle();
                            }
                            break;
                            
                        case "measurement":
                            if (jsonReader.TokenType == System.Text.Json.JsonTokenType.Number)
                            {
                                packet.Measurement = jsonReader.GetSingle();
                            }
                            break;
                    }
                }
            }
            
            _logger.LogDebug("Successfully parsed OnVIF packet: Type={Type}, Description={Description}, Zoom={Zoom}, Measurement={Measurement}", 
                packet.Type, packet.Description, packet.Zoom, packet.Measurement);
            
            return packet;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to parse OnVIF packet of {Length} bytes", payload.Length);
            return null;
        }
    }

    /// <summary>
    /// Handles parsed OnVIF packet by writing it to the channel
    /// </summary>
    private async Task HandleOnVIFPacket(OnVIFPacketEntity packet)
    {
        try
        {
            if (packet == null) return;

            // Write to channel for batch processing
            await _channel.Writer.WriteAsync(packet);
            
            _logger.LogDebug("OnVIF packet queued for batch processing: {PacketId}", packet.Id);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to handle OnVIF packet: {PacketId}", packet?.Id);
        }
    }
}
