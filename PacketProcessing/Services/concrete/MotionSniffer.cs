using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using PacketProcessing.Config;
using PacketProcessing.Model;
using PacketProcessing.Services;
using SharpPcap.LibPcap;

public class MotionSniffer : SnifferBackgroundService<MotionPacket>
{
    private readonly ILogger<MotionSniffer> _typedLogger;

    public MotionSniffer(
        IOptions<ApplicationOptions.SnifferDefinition> snifferDefinition,
        ConcurrentDictionary<string, LibPcapLiveDevice> activeDevices,
        ILogger<SnifferBackgroundService<MotionPacket>> baseLogger,
        ILogger<MotionSniffer> typedLogger)
        : base(snifferDefinition, activeDevices, baseLogger)
    {
        _typedLogger = typedLogger;
        _typedLogger.LogInformation("MotionSniffer initialized");
    }

    protected override IEnumerable<LibPcapLiveDevice> SelectDevices(IEnumerable<LibPcapLiveDevice> all)
    => all;

    protected override string? GetFilter() => string.IsNullOrWhiteSpace(_snifferDefinition.Filter)
    ? "udp" // default
    : _snifferDefinition.Filter;

    protected override Func<ReadOnlyMemory<byte>, MotionPacket?> PacketParser => (payload, info) =>
    {
        return new MotionPacket
        {
            Timestamp = info.Timestamp,
            SourceIp = info.SourceIp,
            DestinationIp = info.DestinationIp,
            SourcePort = info.SourcePort,
            DestinationPort = info.DestinationPort,
            Length = info.Length,
            Protocol = info.Protocol,
            DeviceName = info.DeviceName,
            Payload = payload,
        };
    };

        protected override Func<MotionPacket, Task> PacketHandler => async (p) =>
    {
        if ((p.Id.GetHashCode() & 0xFF) == 0) // sample log
        {
            _typedLogger.LogDebug("MotionPacket {Id} {Src}->{Dst} len={Len} mv={MV}",
                p.Id, p.SourceIp, p.DestinationIp, p.Length, p.MotionValue);
        }

        await Task.CompletedTask;
    };
}