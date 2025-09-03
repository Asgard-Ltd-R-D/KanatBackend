using PacketProcessing.Entities.Packet;
using PacketProcessing.Utils;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Threading.Channels;

namespace PacketProcessing.Services.Networking;

/// <summary>
/// OnVIF packet capture service
/// Captures OnVIF packets and writes them to the OnVIF channel
/// </summary>
public sealed class OnVIFCaptureService : BaseCaptureService<OnVIFPacketEntity>
{
    public OnVIFCaptureService(
        ILogger<OnVIFCaptureService> logger,
        IConfiguration configurationManager,
        Channel<OnVIFPacketEntity> channel)
        : base(logger, configurationManager, channel, "OnVIFCapture")
    {
        // Set up packet parser and handler
        _packetParser = ParseOnVIFPacket;
        _packetHandler = HandleOnVIFPacket;
    }

    /// <summary>
    /// Parses raw packet data into an OnVIFPacketEntity - optimized for high throughput
    /// </summary>
    internal OnVIFPacketEntity ParseOnVIFPacket(ReadOnlySpan<byte> rawPacket)
    {
        // Fast path - minimal checks for performance
        if (rawPacket.IsEmpty) return null!;

        var packet = Parsers.Map<OnVIFPacketEntity>(_protocol, rawPacket);
        if (packet == null) return null!;

        // Notify observers after successful parsing
        NotifyObservers(packet);

        return packet;
    }

    /// <summary>
    /// Handles parsed OnVIF packet by writing it to the channel - optimized for high throughput
    /// </summary>
    internal ValueTask HandleOnVIFPacket(OnVIFPacketEntity packet)
    {
        if (packet is null) return default;
        return _channel.Writer.WriteAsync(packet);
    }
}
