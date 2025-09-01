using PacketProcessing.Entities.Packet;
using PacketProcessing.Utils;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Threading.Channels;

namespace PacketProcessing.Services.Networking;

/// <summary>
/// Motion packet capture service
/// Captures motion packets and writes them to the motion channel
/// </summary>
public sealed class MotionCaptureService : BaseCaptureService<MotionPacketEntity>
{
    public MotionCaptureService(
        ILogger<MotionCaptureService> logger,
        IConfiguration configurationManager,
        Channel<MotionPacketEntity> channel)
        : base(logger, configurationManager, channel, "MotionCapture")
    {
        // Set up packet parser and handler
        _packetParser = ParseMotionPacket;
        _packetHandler = HandleMotionPacket;
    }

    /// <summary>
    /// Parses raw packet data into a MotionPacketEntity using direct TCP parsing
    /// </summary>
    internal MotionPacketEntity ParseMotionPacket(ReadOnlySpan<byte> rawPacket)
    {
        try
        {
            if (rawPacket.IsEmpty)
            {
                _logger.LogWarning("Motion packet empty");
                return null!;
            }

            var packet = Parsers.Map<MotionPacketEntity>(_protocol, rawPacket);
            if (packet == null)
            {
                _logger.LogWarning("Failed to parse motion packet from raw data");
                return null!;
            }

            _logger.LogDebug("Parsed motion packet: Type={Type}, OpCode={OpCode}, Axis={Axis}, FloatValue={FloatValue}",
                packet.Type, packet.OpCode, packet.Axis, packet.FloatValue);

            // Notify observers after successful parsing
            NotifyObservers(packet);

            return packet;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to parse motion packet of {Length} bytes", rawPacket.Length);
            return null!;
        }
    }

    /// <summary>
    /// Handles parsed motion packet by writing it to the channel
    /// </summary>
    internal ValueTask HandleMotionPacket(MotionPacketEntity packet)
    {
        if (packet is null) return default;
        _logger.LogDebug("Motion packet queued for batch processing: {PacketId}", packet.Id);
        return _channel.Writer.WriteAsync(packet);
    }
}
