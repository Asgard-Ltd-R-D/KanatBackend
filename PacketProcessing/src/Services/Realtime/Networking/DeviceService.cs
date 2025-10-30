using System.Buffers;
using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs.Packet;
using PacketProcessing.Services.Realtime.Networking;
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
        
        _logger.LogInformation("[DEVICE-SERVICE] Initialized - Available devices: {Count}", CaptureDeviceList.Instance.Count);
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
                var timestamp = e.GetPacket().Timeval.Date; // The timestamp is the actual captured timestamp of the packet
                var src = raw?.Data;

                if (src is { Length: > 0 })
                {
                    var buf = ArrayPool<byte>.Shared.Rent(src.Length);
                    src.AsSpan().CopyTo(buf.AsSpan(0, src.Length));
                    var mem = new ReadOnlyMemory<byte>(buf, 0, src.Length);      
                                  
                    // Offload to thread pool to avoid blocking packet capture
                    // This prevents slow observers from dropping packets at the OS level
                    _ = Task.Run(() =>
                    {
                        try
                        {
                            // Forward to specific observer
                            observer.OnNext(new RawPacketEvent(dev.Name, mem, timestamp));
                        }
                        catch (Exception ex)
                        {
                    _logger.LogError(ex, "[DEVICE-SERVICE] Error notifying observer {Observer}", observer.GetType().Name);
                        }
                    });
                }
            };
            try
            {
                /*
                    Mode: DeviceModes.Promiscuous capturing all packets on the network.
                    read_timeout: 10000 ms waiting for 10 seconds for a packet to arrive.
                    kernel_buffer_size: 128 MB on Linux for high-throughput (not supported on macOS)
                */
                DeviceConfiguration config = new()
                {
                    Mode = DeviceModes.Promiscuous, // Promiscuous mode for highest throughput
                    ReadTimeout = 10, // 10ms timeout for packet arrival
                    KernelBufferSize = OperatingSystem.IsLinux() ? 1024 * 1024 * 128 : null, // KernelBufferSize only supported on Linux, not macOS
                    Immediate = true // Immediate mode for lowest latency
                };

                dev.Open(config);
                dev.Filter = filter;
                dev.StartCapture();
                if (_activeSubscriptions.TryAdd(observer, dev))
                {
                    _logger.LogInformation("[DEVICE-SERVICE] Observer subscribed on {Device} with filter {Filter}", dev.Name, filter);
                }
                else
                {
                    _logger.LogError("[DEVICE-SERVICE] Failed to add device {Device} to active subscriptions", dev.Name);
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[DEVICE-SERVICE] Error opening device {Device}", dev.Name);
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
                    _logger.LogInformation("[DEVICE-SERVICE] Observer unsubscribed from {Device}", dev.Name);
                }
                catch (Exception ex)
                {
                    _logger.LogWarning(ex, "[DEVICE-SERVICE] Error while cleaning up device {Device}", dev.Name);
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
                    _logger.LogInformation("[DEVICE-SERVICE] Device {Device} stopped and disposed", kvp.Value.Name);
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
        return new ConcurrentUnsubscriber<RawPacketEvent, byte>(_observers, observer);
    }

    #endregion
}
