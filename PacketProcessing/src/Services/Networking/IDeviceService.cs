
using PacketProcessing.DTOs.Packet;

namespace PacketProcessing.Services.Networking;

/// <summary>
/// Event for a raw packet from a device
/// </summary>
/// <param name="DeviceName"></param>
/// <param name="Data"></param>
/// <param name="Timestamp"></param>
public record RawPacketEvent(string DeviceName, ReadOnlyMemory<byte> Data, DateTime Timestamp);


public interface IDeviceService : IObservable<RawPacketEvent>
{
    ICollection<string> GetAvailableDeviceNames();
    Task SubscribeWithFilterAsync(IObserver<RawPacketEvent> obs, string deviceName, string filter);
    Task UnsubscribeAsync(IObserver<RawPacketEvent> obs);
    Task StopAllAsync();
    ICollection<DeviceSubscriptionStatusDto> GetStatus();
}