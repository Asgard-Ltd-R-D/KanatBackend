using PacketProcessing.Entities.Packet;
using PacketProcessing.Utils;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Collections.Concurrent;
using SharpPcap.LibPcap;
using System.Threading.Channels;

namespace PacketProcessing.Services.Networking;

/// <summary>
/// Safety packet capture service
/// Captures safety packets and writes them to the safety channel
/// </summary>
public sealed class SafetyCaptureService : BaseCaptureService<SafetyPacketEntity>
{
    public SafetyCaptureService(
        ILogger<SafetyCaptureService> logger,
        IConfiguration configurationManager,
        Channel<SafetyPacketEntity> channel)
        : base(logger, configurationManager, channel, "SafetyCapture")
    {
        // Set up packet parser and handler
        _packetParser = ParseSafetyPacket;
        _packetHandler = HandleSafetyPacket;
    }

    /// <summary>
    /// Parses raw packet data into a SafetyPacketEntity
    /// </summary>
    internal SafetyPacketEntity ParseSafetyPacket(ReadOnlySpan<byte> rawPacket)
    {
        try
        {
            if (rawPacket.IsEmpty)
            {
                _logger.LogWarning("Safety packet empty");
                return null!;
            }

            var packet = Parsers.Map<SafetyPacketEntity>(_protocol, rawPacket);
            if (packet == null)
            {
                _logger.LogWarning("Failed to parse safety packet from raw data");
                return null!;
            }

            _logger.LogDebug("Parsed safety packet: Type={Type}, OpCode={OpCode}, State={State}",
                packet.Type, packet.OpCode, packet.State);

            return packet;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to parse safety packet of {Length} bytes", rawPacket.Length);
            return null!;
        }
    }

    /// <summary>
    /// Handles parsed safety packet by writing it to the channel
    /// </summary>
    internal ValueTask HandleSafetyPacket(SafetyPacketEntity packet)
    {
        if (packet is null) return default;
        _logger.LogDebug("Safety packet queued for batch processing: {PacketId}", packet.Id);
        return _channel.Writer.WriteAsync(packet);
    }
}
