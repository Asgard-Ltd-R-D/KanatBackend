using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Collections.Concurrent;
using SharpPcap.LibPcap;

namespace PacketProcessing.Services.Networking;

/// <summary>
/// Motion packet capture service
/// Captures motion packets and writes them to the motion channel
/// </summary>
public class MotionCaptureService : BaseCaptureService<MotionPacketEntity>
{
    public MotionCaptureService(
        ILogger<MotionCaptureService> logger,
        IConfiguration configurationManager,
        ConcurrentDictionary<string, LibPcapLiveDevice> activeDevices)
        : base(logger, configurationManager, "MotionCapture", activeDevices)
    {
        // Set up packet parser and handler
        PacketParser = ParseMotionPacket;
        PacketHandler = HandleMotionPacket;
    }

    /// <summary>
    /// Parses raw packet data into a MotionPacketEntity
    /// </summary>
    private MotionPacketEntity ParseMotionPacket(ReadOnlyMemory<byte> payload)
    {
        try
        {
            var span = payload.Span;
            
            // Validate minimum packet size
            if (span.Length < 10) // Minimum size for JSON packet
            {
                _logger.LogWarning("Motion packet too short: {Length} bytes", span.Length);
                return null;
            }
            
            var packet = new MotionPacketEntity
            {
                Id = Guid.NewGuid(),
                Timestamp = DateTime.UtcNow,
                Type = false,
                OpCode = string.Empty,
                OpCodeDescription = string.Empty,
                Axis = 0
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
                            
                        case "opcode":
                            if (jsonReader.TokenType == System.Text.Json.JsonTokenType.String)
                            {
                                packet.OpCode = jsonReader.GetString() ?? string.Empty;
                            }
                            break;
                            
                        case "opcodedescription":
                            if (jsonReader.TokenType == System.Text.Json.JsonTokenType.String)
                            {
                                packet.OpCodeDescription = jsonReader.GetString() ?? string.Empty;
                            }
                            break;
                            
                        case "axis":
                            if (jsonReader.TokenType == System.Text.Json.JsonTokenType.Number)
                            {
                                packet.Axis = jsonReader.GetInt32();
                            }
                            break;
                            
                        case "floatvalue":
                            if (jsonReader.TokenType == System.Text.Json.JsonTokenType.Number)
                            {
                                packet.FloatValue = jsonReader.GetSingle();
                            }
                            break;
                    }
                }
            }
            
            _logger.LogDebug("Successfully parsed motion packet: Type={Type}, OpCode={OpCode}, Axis={Axis}, FloatValue={FloatValue}", 
                packet.Type, packet.OpCode, packet.Axis, packet.FloatValue);
            
            return packet;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to parse motion packet of {Length} bytes", payload.Length);
            return null;
        }
    }

    /// <summary>
    /// Handles parsed motion packet by writing it to the channel
    /// </summary>
    private async Task HandleMotionPacket(MotionPacketEntity packet)
    {
        try
        {
            if (packet == null) return;

            // Write to channel for batch processing
            await _channel.Writer.WriteAsync(packet);
            
            _logger.LogDebug("Motion packet queued for batch processing: {PacketId}", packet.Id);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to handle motion packet: {PacketId}", packet?.Id);
        }
    }
}
