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
    /// Parses raw packet data into an OnVIFPacketEntity
    /// </summary>
    internal OnVIFPacketEntity ParseOnVIFPacket(ReadOnlySpan<byte> rawPacket)
    {
        try
        {
            if (rawPacket.IsEmpty)
            {
                _logger.LogWarning("OnVIF packet empty");
                return null!;
            }

            var packet = Parsers.Map<OnVIFPacketEntity>(_protocol, rawPacket);
            if (packet == null)
            {
                _logger.LogWarning("Failed to parse OnVIF packet from raw data");
                return null!;
            }

            _logger.LogDebug("Parsed OnVIF packet: Type={Type}, Description={Description}, Zoom={Zoom}",
                packet.Type, packet.Description, packet.Zoom);

            // Notify observers after successful parsing
            NotifyObservers(packet);

            return packet;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to parse OnVIF packet of {Length} bytes", rawPacket.Length);
            return null!;
        }
    }

    /// <summary>
    /// Handles parsed OnVIF packet by writing it to the channel
    /// </summary>
    internal ValueTask HandleOnVIFPacket(OnVIFPacketEntity packet)
    {
        if (packet is null) return default;
        _logger.LogDebug("OnVIF packet queued for batch processing: {PacketId}", packet.Id);
        return _channel.Writer.WriteAsync(packet);
    }
}
