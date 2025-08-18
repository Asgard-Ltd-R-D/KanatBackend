using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using PacketProcessing.Interfaces;
using PacketProcessing.Models;
using SharpPcap;
using SharpPcap.LibPcap;
using System.Collections.Concurrent;

namespace PacketProcessing.Services;

public class PacketCaptureWorker : BackgroundService
{
    private readonly ILogger<PacketCaptureWorker> _logger;
    private readonly IPacketStorage _packetStorage;
    private readonly ConcurrentDictionary<string, LibPcapLiveDevice> _activeDevices;
    private readonly string _filter;
    private readonly int _port;

    public PacketCaptureWorker(
        ILogger<PacketCaptureWorker> logger,
        IPacketStorage packetStorage,
        string filter = "udp",
        int port = 5000)
    {
        _logger = logger;
        _packetStorage = packetStorage;
        _filter = filter;
        _port = port;
        _activeDevices = new ConcurrentDictionary<string, LibPcapLiveDevice>();
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        try
        {
            var devices = CaptureDeviceList.Instance;
            if (devices.Count == 0)
            {
                _logger.LogError("No capture devices found. Install libpcap/Npcap.");
                return;
            }

            _logger.LogInformation("Available devices: {Count}", devices.Count);
            foreach (var device in devices)
            {
                _logger.LogInformation("Device: {Name} - {Description}", device.Name, device.Description);
            }

            var captureTasks = new List<Task>();
            foreach (var device in devices)
            {
                if (device is LibPcapLiveDevice liveDevice)
                {
                    captureTasks.Add(StartCaptureOnDeviceAsync(liveDevice, stoppingToken));
                }
            }

            await Task.WhenAll(captureTasks);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error in packet capture worker");
        }
    }

    private async Task StartCaptureOnDeviceAsync(LibPcapLiveDevice device, CancellationToken stoppingToken)
    {
        try
        {
            device.Open(DeviceModes.Promiscuous);
            device.Filter = $"{_filter} port {_port}";

            if (_activeDevices.TryAdd(device.Name ?? Guid.NewGuid().ToString("N"), device))
            {
                _logger.LogInformation("Started capturing on device {Name} with filter: {Filter}", device.Name, device.Filter);
            }

            device.OnPacketArrival += (sender, e) =>
            {
                try
                {
                    var packet = ParsePacket(e, device.Name ?? string.Empty);
                    if (packet != null)
                    {
                        _logger.LogDebug("Captured packet from device {DeviceName} with length {Length}", device.Name, packet.Length);
                        // fire-and-forget to avoid blocking the capture thread
                        _ = _packetStorage.StorePacketAsync(packet);
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Error processing packet from device {DeviceName}", device.Name);
                }
            };

            device.StartCapture();

            while (!stoppingToken.IsCancellationRequested)
            {
                await Task.Delay(1000, stoppingToken);
            }

            device.StopCapture();
            device.Close();
            _logger.LogInformation("Stopped capturing on device {Name}", device.Name);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error starting capture on device {Name}", device.Name);
        }
        finally
        {
            // remove from active map
            var key = _activeDevices.FirstOrDefault(kv => kv.Value == device).Key;
            if (key != null)
            {
                _activeDevices.TryRemove(key, out _);
            }
        }
    }

    // NOTE: changed from `dynamic` to the real type `PacketCapture`
    private PacketData? ParsePacket(PacketCapture e, string deviceName)
    {
        try
        {
            var rawPacket = e.GetPacket(); // returns RawCapture
            if (rawPacket == null) return null;

            var packetData = rawPacket.Data;
            if (packetData == null) return null;

            // Minimal mapping (placeholders for now)
            return new PacketData
            {
                Length = packetData.Length,
                Protocol = "UDP",
                Payload = packetData,
                DeviceName = deviceName,
                SourceIp = "0.0.0.0",
                DestinationIp = "0.0.0.0",
                SourcePort = 0,
                DestinationPort = 0
            };
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Error parsing packet from device {DeviceName}", deviceName);
            return null;
        }
    }

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        _logger.LogInformation("Stopping packet capture worker...");

        foreach (var kv in _activeDevices)
        {
            var device = kv.Value;
            try
            {
                device.StopCapture();
                device.Close();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error stopping device {Name}", device.Name);
            }
        }

        _activeDevices.Clear();
        await base.StopAsync(cancellationToken);
    }
}
