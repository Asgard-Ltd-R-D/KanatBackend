using Microsoft.Extensions.Logging;
using SharpPcap;
using SharpPcap.LibPcap;

namespace PacketProcessing.Services.Networking;

public record RawPacketEvent(string DeviceName, ReadOnlyMemory<byte> Data);

public sealed class DeviceManager
{
    private readonly ILogger<DeviceManager> _logger;
    private readonly ICollection<LibPcapLiveDevice> _devices = [];
    private readonly ICollection<IObserver<RawPacketEvent>> _observers = [];

    public DeviceManager(ILogger<DeviceManager> logger)
    {
        _logger = logger;
    }

    public void InitializeDevices()
    {
        var baseList = CaptureDeviceList.Instance.OfType<LibPcapLiveDevice>().ToList();
        if (baseList.Count == 0)
        {
            _logger.LogError("No capture devices found. Install libpcap/Npcap.");
            return;
        }

        foreach (var dev in baseList)
        {
            try
            {
                dev.OnPacketArrival += (s, e) =>
                {
                    var raw = e.GetPacket();
                    if (raw?.Data is { Length: > 0 } data)
                    {
                        var evt = new RawPacketEvent(dev.Name, data);
                        NotifyObservers(evt);
                    }
                };
                _devices.Add(dev);
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to attach to device {DeviceName}", dev.Name);
            }
        }

        _logger.LogInformation("Initialized {Count} devices: {Devices}",
            _devices.Count, string.Join(", ", _devices.Select(d => d.Name)));
    }

    public void StartAll()
    {
        foreach (var dev in _devices)
        {
            try
            {
                _logger.LogInformation("Opening {Device}", dev.Name);
                dev.Open(DeviceModes.None, read_timeout: 10);
                dev.StartCapture();
                _logger.LogInformation("Device {Device} started capture", dev.Name);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to start capture on {Device}", dev.Name);
            }
        }
    }

    public void StopAll()
    {
        foreach (var dev in _devices)
        {
            try { if (dev.Started) dev.StopCapture(); } catch { }
            try { dev.Close(); } catch { }
        }
        _devices.Clear();
    }

    public void Subscribe(IObserver<RawPacketEvent> obs) => _observers.Add(obs);

    private void NotifyObservers(RawPacketEvent evt)
    {
        foreach (var obs in _observers)
        {
            try { obs.OnNext(evt); }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error notifying observer {Observer}", obs.GetType().Name);
            }
        }
    }
}
