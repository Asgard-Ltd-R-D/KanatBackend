namespace PacketProcessing.Services;

public abstract class SnifferBackgroundService : BackgroundService
{
    private readonly SnifferDefinition _snifferDefinition;
    private readonly ConcurrentDictionary<string, LibPcapLiveDevice> _activeDevices;
}