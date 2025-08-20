using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using PacketProcessing.Config;
using PacketProcessing.Model;
using PacketProcessing.Services;
using SharpPcap.LibPcap;

public class MotionSniffer : SnifferBackgroundService
{
    public MotionSniffer(
        IOptions<ApplicationOptions.SnifferDefinition> snifferDefinition, 
        ConcurrentDictionary<string, LibPcapLiveDevice> activeDevices, 
        ILogger<SnifferBackgroundService> logger) : base(snifferDefinition, activeDevices, logger)
    {
        _logger.LogInformation("MotionSniffer initialized");
    }

    public void SetPacketParser() {
        base.SetPacketParser();
    }

    public void SetPacketHandler() {
        base.SetPacketHandler();
    }
}