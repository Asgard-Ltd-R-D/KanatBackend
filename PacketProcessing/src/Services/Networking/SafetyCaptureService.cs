using PacketProcessing.Entities.Packet;
using PacketProcessing.Utils.Parsers;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
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
    /// Parses raw packet data into a SafetyPacketEntity - optimized for high throughput
    /// </summary>
    internal SafetyPacketEntity ParseSafetyPacket(ReadOnlySpan<byte> rawPacket)
    {
        // Fast path - minimal checks for performance
        if (rawPacket.IsEmpty) return null!;

        var packet = ParseMapper.Map<SafetyPacketEntity>(rawPacket);
        if (packet == null) return null!;

        // Notify observers after successful parsing
        NotifyObservers(packet);

        return packet;
    }

    /// <summary>
    /// Handles parsed safety packet by writing it to the channel - optimized for high throughput
    /// </summary>
    internal ValueTask HandleSafetyPacket(SafetyPacketEntity packet)
    {
        if (packet is null) return default;
        return _channel.Writer.WriteAsync(packet);
    }
}
