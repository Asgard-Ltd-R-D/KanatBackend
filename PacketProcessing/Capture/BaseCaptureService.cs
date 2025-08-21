using System.Collections.Concurrent;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using SharpPcap;
using SharpPcap.LibPcap;

namespace PacketProcessing.Capture;

public abstract class BaseCaptureService<T>(
    string snifferName,
    string protocol,
    List<string> ips,
    ConcurrentDictionary<string, LibPcapLiveDevice> activeDevices,
    ILogger<BaseCaptureService<T>> logger)
    : BackgroundService, ICapture<T>
    where T : class
{
    protected abstract Func<ReadOnlyMemory<byte>, T?> PacketParser { get; set; }
    protected abstract Func<T, Task> PacketHandler { get; set; }
    
    public required string _protocol = protocol;
    public required List<string> _ips = [..ips];
    
    public string Protocol { get => _protocol; set => _protocol = string.IsNullOrWhiteSpace(value) ? "ip" : value.Trim(); }
    public IReadOnlyList<string> Ips { get => _ips; set => _ips = [..value]; }
    
    public void SetPacketParser(Func<ReadOnlyMemory<byte>, T?> parser) => PacketParser = parser ?? throw new ArgumentNullException(nameof(parser));
    public void SetPacketHandler(Func<T, Task> handler) => PacketHandler = handler ?? throw new ArgumentNullException(nameof(handler));
    
    protected virtual string GetFilter()
    {
        var proto = string.IsNullOrWhiteSpace(_protocol) ? "ip" : _protocol.Trim();
        if (_ips.Count == 0) return proto;

        var ipExpr = string.Join(" or ", _ips.Select(ip => $"host {ip}"));
        return $"{proto} and ({ipExpr})";
    }

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        try
        {
            logger.LogInformation("Starting sniffer '{SnifferName}' with filter: {Filter}", _snifferName, GetFilter());

            var all = CaptureDeviceList.Instance.OfType<LibPcapLiveDevice>().ToList();
            if (all.Count == 0)
            {
                logger.LogError("No capture devices found. Install libpcap/Npcap.");
                return;
            }

            var devices = activeDevices.Values.ToList();
            if (devices.Count == 0)
            {
                logger.LogWarning("No devices selected for sniffer '{SnifferName}'.", _snifferName);
                return;
            }

            // Start capture on all selected devices
            var tasks = new List<Task>(devices.Count);
            tasks.AddRange(devices.Select(dev => StartCaptureOnDeviceAsync(dev, ct)));
            
            await Task.WhenAll(tasks);
        }
        catch (OperationCanceledException) { /* normal on shutdown */ }
        catch (Exception ex)
        {
            logger.LogError(ex, "Error in packet capture worker for sniffer '{SnifferName}'", _snifferName);
        }
    }

    private async Task StartCaptureOnDeviceAsync(LibPcapLiveDevice device, CancellationToken ct)
    {
        var key = device.Name;

        try
        {
            device.Open(DeviceModes.Promiscuous, read_timeout: 1);

            var filter = GetFilter();
            if (!string.IsNullOrWhiteSpace(filter))
                device.Filter = filter;

            if (activeDevices.TryAdd(key, device))
            {
                logger.LogInformation("Capturing on device {Name} with filter: {Filter} for '{SnifferName}'",
                    device.Name, device.Filter, _snifferName);
            }

            device.OnPacketArrival += OnPacketArrival;
            device.StartCapture();

            while (!ct.IsCancellationRequested)
                await Task.Delay(250, ct);

            device.StopCapture();
            device.Close();

            logger.LogInformation("Stopped device {Name} for '{SnifferName}'", device.Name, _snifferName);
        }
        catch (OperationCanceledException) { /* normal on shutdown */ }
        catch (Exception ex)
        {
            logger.LogError(ex, "Error starting capture on device {Name} for sniffer '{SnifferName}'", device.Name, _snifferName);
        }
        finally
        {
            if (activeDevices.TryRemove(key, out var dev))
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
            if (sender is not LibPcapLiveDevice) return;

            var raw = e.GetPacket();
            if (raw?.Data is null || raw.Data.Length == 0) return;

            // Zero-copy: wrap raw byte[] as ReadOnlyMemory<byte>
            var payload = new ReadOnlyMemory<byte>(raw.Data);

            var parsed = PacketParser(payload);
            if (parsed is null) return;

            // Delegate handling (storage / pipeline / realtime) to consumer
            _ = Task.Run(async () =>
            {
                try { await PacketHandler(parsed); }
                catch (Exception ex)
                {
                    logger.LogError(ex, "Packet handler failed in '{SnifferName}'", _snifferName);
                }
            });
        }
        catch (Exception ex)
        {
            logger.LogDebug(ex, "OnPacketArrival error in '{SnifferName}'", _snifferName);
        }
    }

    public override void Dispose()
    {
        foreach (var kv in activeDevices)
        {
            var dev = kv.Value;
            try
            {
                try { dev.OnPacketArrival -= OnPacketArrival; } catch { /* ignore */ }
                try { if (dev.Started) dev.StopCapture(); } catch { /* ignore */ }
                try { dev.Close(); } catch { /* ignore */ }
            }
            catch { /* best-effort */ }
        }
        activeDevices.Clear();

        base.Dispose();
    }
}
