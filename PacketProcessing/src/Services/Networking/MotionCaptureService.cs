using PacketProcessing.Entities.Packet;
using PacketProcessing.Utils.Parsers;
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
        // Initialize the parser logger
        MotionPacketParser.SetLogger(logger);
        
        // Set up packet parser and handler
        _packetParser = ParseMotionPacket;
        _packetHandler = HandleMotionPacket;
    }

    /// <summary>
    /// Parses raw packet data into a MotionPacketEntity - optimized for high throughput
    /// </summary>
    internal MotionPacketEntity ParseMotionPacket(ReadOnlySpan<byte> rawPacket)
    {
        // Fast path - minimal checks for performance
        if (rawPacket.IsEmpty) return null!;

        var packet = ParseMapper.Map<MotionPacketEntity>(rawPacket);
        if (packet == null) return null!;

        // Notify observers after successful parsing
        NotifyObservers(packet);

        return packet;
    }

    /// <summary>
    /// Handles parsed motion packet by writing it to the channel - optimized for high throughput
    /// </summary>
    internal ValueTask HandleMotionPacket(MotionPacketEntity packet)
    {
        if (packet is null) return default;
        return _channel.Writer.WriteAsync(packet);
    }
}
