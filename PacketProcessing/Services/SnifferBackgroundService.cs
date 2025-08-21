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

public abstract class SnifferBackgroundService<T> : BackgroundService where T : class
{
    protected readonly ApplicationOptions.SnifferDefinition _snifferDefinition;
    protected readonly ConcurrentDictionary<string, LibPcapLiveDevice> _activeDevices;
    protected readonly ILogger<SnifferBackgroundService> _logger;
    protected readonly string _snifferName;

    protected abstract Func<ReadOnlyMemory<byte>, PacketInfo, T?> PacketParser { get; }
    protected abstract Func<T, Task> PacketHandler { get; }

    public SnifferBackgroundService(
        IOptions<ApplicationOptions.SnifferDefinition> snifferDefinition,
        ConcurrentDictionary<string, LibPcapLiveDevice> activeDevices,
        ILogger<SnifferBackgroundService> logger)
    {
        _snifferDefinition = snifferDefinition.Value;
        _activeDevices = activeDevices;
        _logger = logger;
        _snifferName = _snifferDefinition.Name;
    }

    protected virtual IEnumerable<LibPcapLiveDevice> SelectDevices(IEnumerable<LibPcapLiveDevice> all)
    => all;

    protected virtual string? GetFilter() => _snifferDefinition.Filter;

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        try
        {
            _logger.LogInformation("Starting sniffer '{SnifferName}' with filter: {Filter}", _snifferName, GetFilter());
            
            var all = CaptureDeviceList.Instance.OfType<LibPcapLiveDevice>().ToList();
            if (all.Count == 0)
            {
                _logger.LogError("No capture devices found. Install libpcap/Npcap.");
                return;
            }

            var devices = SelectDevices(all).ToList();
            if (devices.Count == 0)
            {
                _logger.LogWarning("No devices selected for sniffer '{SnifferName}'.", _snifferName);
                return;
            }

            // Start capture on all devices
            var tasks = new List<Task>(devices.Count);
            devices.ForEach(dev => tasks.Add(StartCaptureOnDeviceAsync(dev, ct)));
            await Task.WhenAll(tasks);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error in packet capture worker for sniffer '{SnifferName}'", _snifferName);
        }
    }

    private async Task StartCaptureOnDeviceAsync(LibPcapLiveDevice device, CancellationToken ct)
    {
        string key = device.Name ?? Guid.NewGuid().ToString("N");

        try
        {
            // Open the device, set filter, and set up packet arrival handler
            device.Open(mode, read_timeout: 1);

            var filter = GetFilter();
            if (!string.IsNullOrWhiteSpace(filter))
                device.Filter = filter!;
            
            if (_activeDevices.TryAdd(key, device))
            {
                _logger.LogInformation("Capturing on device {Name} with filter: {Filter} for '{SnifferName}'",
                    device.Name, device.Filter, _snifferName);
            }

            device.OnPacketArrival += OnPacketArrival;
            device.StartCapture();

            while (!ct.IsCancellationRequested)
            {
                await Task.Delay(250, ct);
            }

            device.StopCapture();
            device.Close();
            _logger.LogInformation("Stopped device {Name} for '{SnifferName}'", device.Name, _snifferName);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error starting capture on device {Name} for sniffer '{SnifferName}'", device.Name, _snifferName);
        }
        finally
        {
            if (_activeDevices.TryRemove(key, out var dev))
            {
                try { dev.OnPacketArrival -= OnPacketArrival; } catch { /* ignore */ }
                try { if (dev.Started) dev.StopCapture(); } catch { /* ignore */ }
                try { dev.Close(); } catch { /* ignore */ }
            }
        }
    }

    private void OnPacketArrival(object? sender, PacketCapture e)
    {
        try
        {
            if (sender is not LibPcapLiveDevice dev) return;

            var raw = e.GetPacket();
            if (raw is null || raw.Data is null || raw.Data.Length == 0) return;

            var infoMaybe = PacketUtils.ExtractPacketInfo(e);
            if (infoMaybe is null) return;

            var pi = infoMaybe.Value;
            var info = new PacketInfo(
                pi.timestamp,
                pi.sourceIp,
                pi.destinationIp,
                pi.sourcePort,
                pi.destinationPort,
                pi.length,
                pi.protocol,
                dev.Name ?? "unknown"
            );

            // Zero-copy: wrap raw byte[] as ReadOnlyMemory<byte>
            var payload = new ReadOnlyMemory<byte>(raw.Data);

            var parsed = PacketParser(payload, info);
            if (parsed is null) return;

            _ = Task.Run(async () =>
            {
                try { await PacketHandler(parsed); }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Packet handler failed in '{SnifferName}'", _snifferName);
                }
            });
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "OnPacketArrival error in '{SnifferName}'", _snifferName);
        }
    }

    public override void Dispose()
    {
        foreach (var kv in _activeDevices)
        {
            var dev = kv.Value;
            try
            {
                try { dev.OnPacketArrival -= OnPacketArrival; } catch { }
                try { if (dev.Started) dev.StopCapture(); } catch { }
                try { dev.Close(); } catch { }
            }
            catch { }
        }
        _activeDevices.Clear();

        base.Dispose();
    }
}