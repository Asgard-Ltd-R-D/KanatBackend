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
    
    // Packet counting and deduplication
    private long _totalPacketsCaptured;
    private long _totalPacketsStored;
    private readonly object _statsLock = new object();

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
                        Interlocked.Increment(ref _totalPacketsCaptured);
                        
                        _logger.LogDebug("Captured packet from device {DeviceName} with length {Length}, timestamp {Timestamp}", 
                            device.Name, packet.Length, packet.Timestamp.ToString("HH:mm:ss.ffffff"));
                        
                        // Store packet asynchronously but track completion
                        _ = Task.Run(async () =>
                        {
                            try
                            {
                                await _packetStorage.StorePacketAsync(packet);
                                Interlocked.Increment(ref _totalPacketsStored);
                                
                                // Log statistics periodically
                                if (_totalPacketsStored % 100 == 0)
                                {
                                    LogPacketStatistics();
                                }
                            }
                            catch (Exception storageEx)
                            {
                                _logger.LogError(storageEx, "Failed to store packet {Id} from device {DeviceName}", 
                                    packet.Id, device.Name);
                            }
                        });
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

            // Use PCAP timestamp (when packet was discovered) not system time
            var packetTimestamp = rawPacket.Timeval.Date;
            
            // Parse UDP header (basic parsing)
            var sourcePort = 0;
            var destPort = 0;
            var sourceIp = "0.0.0.0";
            var destIp = "0.0.0.0";
            
            if (packetData.Length >= 8) // Minimum UDP header size
            {
                // UDP header: [0-1] Source Port, [2-3] Destination Port, [4-5] Length, [6-7] Checksum
                sourcePort = (packetData[0] << 8) | packetData[1];
                destPort = (packetData[2] << 8) | packetData[3];
                
                // For now, use placeholder IPs - you can extend this to parse IP headers if needed
                // In a real implementation, you'd parse the IP header to get actual source/dest IPs
            }

            // Create packet data with PCAP timestamp
            return new PacketData
            {
                Id = Guid.NewGuid(), // Generate unique ID for database
                Timestamp = packetTimestamp, // Use PCAP timestamp, not system time
                Length = packetData.Length,
                Protocol = "UDP",
                Payload = packetData,
                DeviceName = deviceName,
                SourceIp = sourceIp,
                DestinationIp = destIp,
                SourcePort = sourcePort,
                DestinationPort = destPort
            };
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Error parsing packet from device {DeviceName}", deviceName);
            return null;
        }
    }

    private void LogPacketStatistics()
    {
        lock (_statsLock)
        {
            _logger.LogInformation("Packet Statistics: Captured {TotalCaptured}, Stored {TotalStored}, Success Rate: {SuccessRate:P1}", 
                _totalPacketsCaptured, _totalPacketsStored, 
                _totalPacketsCaptured > 0 ? (double)_totalPacketsStored / _totalPacketsCaptured : 0.0);
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
