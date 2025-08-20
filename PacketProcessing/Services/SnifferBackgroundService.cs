using System.Collections.Concurrent;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using PacketProcessing.Config;
using PacketProcessing.Model;
using PacketProcessing.Utils;
using SharpPcap;
using SharpPcap.LibPcap;

namespace PacketProcessing.Services;

public class SnifferBackgroundService : BackgroundService
{
    private readonly ApplicationOptions.SnifferDefinition _snifferDefinition;
    private readonly ConcurrentDictionary<string, LibPcapLiveDevice> _activeDevices;
    private readonly ILogger<SnifferBackgroundService> _logger;
    private readonly Func<byte[], ulong, string, string, int, int, int, string, BasePacket?> _packetParser;
    private readonly Func<BasePacket, Task> _packetHandler;
    private readonly string _snifferName;

    public SnifferBackgroundService(
        IOptions<ApplicationOptions.SnifferDefinition> snifferDefinition,
        ConcurrentDictionary<string, LibPcapLiveDevice> activeDevices,
        ILogger<SnifferBackgroundService> logger,
        Func<byte[], ulong, string, string, int, int, int, string, BasePacket?> packetParser,
        Func<BasePacket, Task> packetHandler)
    {
        _snifferDefinition = snifferDefinition.Value;
        _activeDevices = activeDevices;
        _logger = logger;
        _packetParser = packetParser;
        _packetHandler = packetHandler;
        _snifferName = _snifferDefinition.Name;
    }

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        try
        {
            _logger.LogInformation("Starting sniffer '{SnifferName}' with filter: {Filter}", _snifferName, _snifferDefinition.Filter);
            
            var devices = CaptureDeviceList.Instance;
            if (devices.Count == 0)
            {
                _logger.LogError("No capture devices found. Install libpcap/Npcap.");
                return;
            }

            _logger.LogInformation("Available devices: {Count}", devices.Count);

            var captureTasks = new List<Task>();
            foreach (var device in devices)
            {
                if (device is LibPcapLiveDevice liveDevice)
                {
                    captureTasks.Add(StartCaptureOnDeviceAsync(liveDevice, ct));
                }
            }

            await Task.WhenAll(captureTasks);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error in packet capture worker for sniffer '{SnifferName}'", _snifferName);
        }
    }

    private async Task StartCaptureOnDeviceAsync(LibPcapLiveDevice device, CancellationToken stoppingToken)
    {
        try
        {
            device.Open(DeviceModes.Promiscuous);
            device.Filter = _snifferDefinition.Filter;

            if (_activeDevices.TryAdd(device.Name ?? Guid.NewGuid().ToString("N"), device))
            {
                _logger.LogInformation("Started capturing on device {Name} with filter: {Filter} for sniffer '{SnifferName}'", 
                    device.Name, device.Filter, _snifferName);
            }

            device.OnPacketArrival += OnPacketArrival;

            device.StartCapture();

            while (!stoppingToken.IsCancellationRequested)
            {
                await Task.Delay(1000, stoppingToken);
            }

            device.StopCapture();
            device.Close();
            _logger.LogInformation("Stopped capturing on device {Name} for sniffer '{SnifferName}'", device.Name, _snifferName);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error starting capture on device {Name} for sniffer '{SnifferName}'", device.Name, _snifferName);
        }
        finally
        {
            var key = _activeDevices.FirstOrDefault(kv => kv.Value == device).Key;
            if (key != null)
            {
                _activeDevices.TryRemove(key, out _);
            }
        }
    }

    protected void StartDevices()
    {
        foreach (var (key, dev) in _activeDevices)
        {
            try
            {
                dev.Open(DeviceModes.Promiscuous, read_timeout: 1);
                if (!string.IsNullOrWhiteSpace(_snifferDefinition.Filter))
                    dev.Filter = _snifferDefinition.Filter;

                dev.OnPacketArrival += OnPacketArrival;
                dev.StartCapture();
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to start capture on device '{Device}' for sniffer '{SnifferName}'", dev.Name, _snifferName);
                try { dev.Close(); } catch { /* ignore */ }
            }
        }
    }

    protected void StopDevices()
    {
        foreach (var kv in _activeDevices)
        {
            var dev = kv.Value;
            try
            {
                try { dev.OnPacketArrival -= OnPacketArrival; } catch { /* ignore */ }
                try { if (dev.Started) dev.StopCapture(); } catch { /* ignore */ }
                try { dev.Close(); } catch { /* ignore */ }
            }
            catch (Exception ex)
            {
                _logger.LogDebug(ex, "Error while stopping device '{Device}' for sniffer '{SnifferName}'", kv.Key, _snifferName);
            }
        }
        _activeDevices.Clear();
    }

    private void OnPacketArrival(object? sender, PacketCapture e)
    {
        try
        {
            if (sender is LibPcapLiveDevice dev)
            {
                HandlePacket(dev, e);
            }
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "HandlePacket threw in sniffer '{SnifferName}'", _snifferName);
        }
    }

    private void HandlePacket(LibPcapLiveDevice device, PacketCapture e)
    {
        try
        {
            var basePacket = new BasePacket();
            var raw = e.GetPacket();
            if (raw == null) 
            {
                _logger.LogError("Failed to get packet from capture {CaptureId}", basePacket.Id);
                return;
            }

            (
                ulong timestamp, 
                string sourceIp, 
                string destinationIp, 
                int sourcePort, 
                int destinationPort, 
                int length, 
                string protocol
            )? packetInfo = PacketUtils.ExtractPacketInfo(e);

            if (packetInfo == null) 
            {
                _logger.LogError("Failed to extract packet info from packet {PacketId}", basePacket.Id);
                return;
            }

            // Parse the packet using the configured parser
            var packetData = raw.Data;
            var parsedPacket = 
            _packetParser(
                packetData, 
                packetInfo.GetValueOrDefault().timestamp,
                packetInfo.GetValueOrDefault().sourceIp, 
                packetInfo.GetValueOrDefault().destinationIp, 
                packetInfo.GetValueOrDefault().sourcePort, 
                packetInfo.GetValueOrDefault().destinationPort,
                packetInfo.GetValueOrDefault().length,
                packetInfo.GetValueOrDefault().protocol,
                device.Name ?? "unknown"
            );
            
            if (parsedPacket != null)
            {
                // Handle the packet asynchronously
                _ = Task.Run(async () =>
                {
                    try
                    {
                        await _packetHandler(parsedPacket);
                    }
                    catch (Exception ex)
                    {
                        _logger.LogError(ex, "Error handling packet in sniffer '{SnifferName}'", _snifferName);
                    }
                });
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error parsing packet in sniffer '{SnifferName}'", _snifferName);
        }
    }

    public override void Dispose()
    {
        StopDevices();
        base.Dispose();
    }
}