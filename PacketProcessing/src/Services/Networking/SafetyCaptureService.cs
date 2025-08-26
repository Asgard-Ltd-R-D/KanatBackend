using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Collections.Concurrent;
using SharpPcap.LibPcap;

namespace PacketProcessing.Services.Networking;

/// <summary>
/// Safety packet capture service
/// Captures safety packets and writes them to the safety channel
/// </summary>
public class SafetyCaptureService : BaseCaptureService<SafetyPacketEntity>
{
    public SafetyCaptureService(
        ILogger<SafetyCaptureService> logger,
        IConfiguration configurationManager,
        ConcurrentDictionary<string, LibPcapLiveDevice> activeDevices)
        : base(logger, configurationManager, "SafetyCapture", activeDevices)
    {
        // Set up packet parser and handler
        PacketParser = ParseSafetyPacket;
        PacketHandler = HandleSafetyPacket;
    }

    /// <summary>
    /// Parses raw packet data into a SafetyPacketEntity
    /// </summary>
    private SafetyPacketEntity ParseSafetyPacket(ReadOnlyMemory<byte> payload)
    {
        try
        {
            var span = payload.Span;
            
            // Validate minimum packet size
            if (span.Length < 10) // Minimum size for JSON packet
            {
                _logger.LogWarning("Safety packet too short: {Length} bytes", span.Length);
                return null;
            }
            
            var packet = new SafetyPacketEntity
            {
                Id = Guid.NewGuid(),
                Timestamp = DateTime.UtcNow,
                Type = false,
                OpCode = string.Empty,
                OpCodeDescription = string.Empty,
                State = string.Empty
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
                            
                        case "state":
                            if (jsonReader.TokenType == System.Text.Json.JsonTokenType.String)
                            {
                                packet.State = jsonReader.GetString() ?? string.Empty;
                            }
                            break;
                    }
                }
            }
            

            
            _logger.LogDebug("Successfully parsed safety packet: Type={Type}, OpCode={OpCode}, State={State}", 
                packet.Type, packet.OpCode, packet.State);
            
            return packet;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to parse safety packet of {Length} bytes", payload.Length);
            return null;
        }
    }
    


    /// <summary>
    /// Handles parsed safety packet by writing it to the channel
    /// </summary>
    private async Task HandleSafetyPacket(SafetyPacketEntity packet)
    {
        try
        {
            if (packet == null) return;

            // Write to channel for batch processing
            await _channel.Writer.WriteAsync(packet);
            
            _logger.LogDebug("Safety packet queued for batch processing: {PacketId}", packet.Id);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to handle safety packet: {PacketId}", packet?.Id);
        }
    }
}
