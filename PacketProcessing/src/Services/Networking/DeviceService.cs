using System.Buffers;
using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs.Packet;
using PacketProcessing.Services.Networking;
using PacketProcessing.Utils.Observers;
using SharpPcap;
using SharpPcap.LibPcap;

public class DeviceService : IDeviceService
{
    private readonly ILogger<DeviceService> _logger;

    // Active subscriptions: one device instance per observer
    private readonly ConcurrentDictionary<IObserver<RawPacketEvent>, LibPcapLiveDevice> _activeSubscriptions = new();

    // Keep track of observers explicitly (for IObservable implementation)
    private readonly ConcurrentDictionary<IObserver<RawPacketEvent>, byte> _observers = new();

    public DeviceService(ILogger<DeviceService> logger)
    {
        _logger = logger;
    }

    public ICollection<string> GetAvailableDeviceNames()
    {
        return [.. CaptureDeviceList.Instance.OfType<LibPcapLiveDevice>().Select(d => d.Name)];
    }

    public async Task SubscribeWithFilterAsync(IObserver<RawPacketEvent> observer, string deviceName, string filter)
    {
        await Task.Run(() =>
        {
            var baseDev = CaptureDeviceList.Instance
                .OfType<LibPcapLiveDevice>()
                .FirstOrDefault(d => d.Name == deviceName)
                ?? throw new ArgumentException($"Device {deviceName} not found");

            if (baseDev.Interface == null)
                throw new InvalidOperationException($"Device {deviceName} has no underlying interface");

            var dev = new LibPcapLiveDevice(baseDev.Interface);

            dev.OnPacketArrival += (s, e) =>
            {
                var raw = e.GetPacket();
                var src = raw?.Data;

                if (src is { Length: > 0 })
                {
                    var buf = ArrayPool<byte>.Shared.Rent(src.Length);
                    Buffer.BlockCopy(src, 0, buf, 0, src.Length);
                    var mem = new ReadOnlyMemory<byte>(buf, 0, src.Length);      
                                  
                    try
                    {
                        // Forward to specific observer
                        observer.OnNext(new RawPacketEvent(dev.Name, mem));
                    }
                    catch (Exception ex)
                    {
                        _logger.LogError(ex, "Error notifying observer {Observer}", observer.GetType().Name);
                    }
                }
            };
            try
            {
                dev.Open(DeviceModes.Promiscuous, read_timeout: 10000);
                dev.Filter = filter;
                dev.StartCapture();
                if (_activeSubscriptions.TryAdd(observer, dev))
                {
                    _logger.LogInformation("Observer subscribed on {Device} with filter {Filter}", dev.Name, filter);
                }
                else
                {
                    _logger.LogError("Failed to add device {Device} to active subscriptions", dev.Name);
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error opening device {Device}", dev.Name);
            }


        });
    }

    public async Task UnsubscribeAsync(IObserver<RawPacketEvent> observer)
    {
        await Task.Run(() =>
        {
            if (_activeSubscriptions.TryRemove(observer, out var dev))
            {
                try
                {
                    if (dev.Started) dev.StopCapture();
                    dev.Close();
                    dev.Dispose();
                    _logger.LogInformation("Observer unsubscribed from {Device}", dev.Name);
                }
                catch (Exception ex)
                {
                    _logger.LogWarning(ex, "Error while cleaning up device {Device}", dev.Name);
                }
            }

            _observers.TryRemove(observer, out _);
        });
    }

    public async Task StopAllAsync()
    {
        await Task.Run(() =>
        {
            foreach (var kvp in _activeSubscriptions)
            {
                try
                {
                    if (kvp.Value.Started) kvp.Value.StopCapture();
                    kvp.Value.Close();
                    kvp.Value.Dispose();
                    _logger.LogInformation("Device {Device} stopped and disposed", kvp.Value.Name);
                }
                catch { }
            }

            _activeSubscriptions.Clear();
            _observers.Clear();
        });
    }

    /// <summary>
    /// Returns all active subscriptions with device, filter, and state.
    /// </summary>
    public ICollection<DeviceSubscriptionStatusDto> GetStatus()
    {
        return [.. _activeSubscriptions.Select(kvp =>
        {
            var dev = kvp.Value;
            var filter = dev.Filter;
            return new DeviceSubscriptionStatusDto
            {
                DeviceName = dev.Name,
                Filter = filter ?? "no filter found",
                IsCapturing = dev.Started
            };
        })];
    }

    #region IObservable<RawPacketEvent>

    public IDisposable Subscribe(IObserver<RawPacketEvent> observer)
    {
        ArgumentNullException.ThrowIfNull(observer);
        _observers.TryAdd(observer, 0);
        return new ConcurrentUnsubscriber<RawPacketEvent>(_observers, observer);
    }

    #endregion
}
