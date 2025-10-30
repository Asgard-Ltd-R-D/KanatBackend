using static PacketProcessing.DTOs.Range.RangeDto;

namespace PacketProcessing.Services.Realtime.Networking;

/// <summary>
/// Generic handler interface for processing packets.
/// Extends IObserver to receive raw packets and adds
/// subscription methods for device service binding.
/// </summary>
public interface IHandlerService<T> : IObserver<RawPacketEvent>
{
    /// <summary>
    /// Explicitly subscribes this handler to the given device service.
    /// </summary>
    Task SubscribeToDeviceAsync(IDeviceService deviceService, string deviceName);

    /// <summary>
    /// Subscribes this handler using a full range configuration (device + BPF endpoints).
    /// </summary>
    Task SubscribeToDeviceAsync(IDeviceService deviceService, RangeConfig config);

    /// <summary>
    /// Subscribes this handler using only the BPF configuration (device + endpoints).
    /// </summary>
    Task SubscribeToDeviceAsync(IDeviceService deviceService, PacketProcessing.DTOs.Conf.BPFConfDto bpfConfig);

    /// <summary>
    /// Unsubscribes this handler from the device service.
    /// </summary>
    Task UnsubscribeAsync(IDeviceService deviceService);

    /// <summary>
    /// Gets statistics about processed packets.
    /// </summary>
    (long Captured, long Parsed, long Dropped, double AvgLatencyMs) GetStats();
    
    /// <summary>
    /// Gets the number of backpressure events.
    /// </summary>
    long GetBackpressureEvents();
    
    /// <summary>
    /// Gets the current count of items in the raw channel (capture -> parse) if available.
    /// Returns -1 if count is not available.
    /// </summary>
    int GetRawChannelCount();
    
    /// <summary>
    /// Resets all statistics counters to zero.
    /// </summary>
    void ResetStats();
}
