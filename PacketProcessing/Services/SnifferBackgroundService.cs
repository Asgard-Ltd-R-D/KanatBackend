using System.Collections.Concurrent;
using Microsoft.Extensions.Hosting;
using SharpPcap.LibPcap;
using static PacketProcessing.Config.ApplicationOptions;

namespace PacketProcessing.Services;

public abstract class SnifferBackgroundService : BackgroundService
{
    private readonly SnifferDefinition _snifferDefinition;
    private readonly ConcurrentDictionary<string, LibPcapLiveDevice> _activeDevices;
}