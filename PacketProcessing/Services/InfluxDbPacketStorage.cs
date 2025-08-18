using System.Net.Sockets;
using System.Threading.Channels;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using PacketProcessing.Configuration;
using PacketProcessing.Interfaces;
using PacketProcessing.Models;
using QuestDB;
using QuestDB.Senders;

namespace PacketProcessing.Services;

public class InfluxDbPacketStorage : IPacketStorage, IDisposable
{
    private readonly ILogger<InfluxDbPacketStorage> _logger;
    private readonly InfluxDbOptions _options;

    // Shared input channel
    private readonly Channel<PacketData> _packetChannel;

    // Autoscaling worker pool
    private readonly List<Task> _workerTasks = [];
    private readonly List<CancellationTokenSource> _workerCts = [];
    private readonly CancellationTokenSource _cts = new();

    // Connection string: use TCP ILP for throughput
    private readonly string _connectionString;

    // Backlog estimator (atomic) for autoscaling
    private int _queuedCount;

    // Autoscaler knobs (you can move these into configuration if you like)
    private readonly int _minWorkers = 1;
    private readonly int _maxWorkers = 4;
    private readonly int _scaleUpBacklog = 10_000;   // if backlog > this -> scale up (and RAM ok)
    private readonly int _scaleDownBacklog = 2_000;  // if backlog < this -> scale down
    private readonly long _maxRamBytes = 2L * 1024 * 1024 * 1024; // 2GB (soft limit)

    public InfluxDbPacketStorage(
        ILogger<InfluxDbPacketStorage> logger,
        IOptions<InfluxDbOptions> options)
    {
        _logger = logger;
        _options = options.Value;

        // Strongly recommend HTTP ILP (default QuestDB ILP is 9009)
        _connectionString =
            $"http::addr={_options.Host}:{_options.Port};username={_options.Username};password={_options.Password};" +
            $"auto_flush_rows={_options.BatchSize};auto_flush_interval={_options.BatchTimeoutMs};";

        // Bounded channel big enough to absorb bursts
        _packetChannel = Channel.CreateBounded<PacketData>(new BoundedChannelOptions(_options.BatchSize * 5000)
        {
            FullMode = BoundedChannelFullMode.Wait,
            SingleReader = false,
            SingleWriter = false
        });

        // Start with min workers
        for (int i = 0; i < _minWorkers; i++)
            StartWorker();

        // Kick off autoscaler
        _ = Task.Run(AutoscalerLoopAsync, _cts.Token);

        _logger.LogInformation(
            "QuestDB ILP Storage (multi-sender): TCP {Host}:{Port}, BatchSize={BatchSize}, Interval={Interval}ms, Workers={Min}..{Max}",
            _options.Host, _options.Port, _options.BatchSize, _options.BatchTimeoutMs, _minWorkers, _maxWorkers);
    }

    // Producer API -------------------------------------------------------------

    public async Task StorePacketAsync(PacketData packet)
    {
        try
        {
            await _packetChannel.Writer.WriteAsync(packet, _cts.Token);
            Interlocked.Increment(ref _queuedCount);
        }
        catch (OperationCanceledException) { /* shutting down */ }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error enqueuing packet {Id}", packet.Id);
        }
    }

    public async Task StorePacketsBatchAsync(IEnumerable<PacketData> packets)
    {
        try
        {
            foreach (var p in packets)
            {
                await _packetChannel.Writer.WriteAsync(p, _cts.Token);
                Interlocked.Increment(ref _queuedCount);
            }
        }
        catch (OperationCanceledException) { /* shutting down */ }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error enqueuing batch of {Count} packets", packets.Count());
        }
    }

    public Task<IEnumerable<PacketData>> GetPacketsAsync(DateTime from, DateTime to, int limit = 1000)
        => Task.FromResult<IEnumerable<PacketData>>(Enumerable.Empty<PacketData>());

    public Task<long> GetPacketCountAsync(DateTime from, DateTime to)
        => Task.FromResult(0L);

    // Workers & Autoscaler -----------------------------------------------------

    private void StartWorker()
    {
        var cts = new CancellationTokenSource();
        _workerCts.Add(cts);
        var task = Task.Run(() => WorkerLoopAsync(cts.Token), cts.Token);
        _workerTasks.Add(task);
    }

    private void StopOneWorker()
    {
        if (_workerCts.Count == 0) return;
        var cts = _workerCts[^1];
        _workerCts.RemoveAt(_workerCts.Count - 1);
        cts.Cancel();
        // Let task finish; Dispose() will wait briefly for all
    }

    private async Task AutoscalerLoopAsync()
    {
        while (!_cts.IsCancellationRequested)
        {
            try
            {
                // Snapshot queue depth and memory
                int depth = Volatile.Read(ref _queuedCount);
                long mem = GC.GetTotalMemory(forceFullCollection: false);

                // Scale up
                if (depth > _scaleUpBacklog && mem < _maxRamBytes && _workerCts.Count < _maxWorkers)
                {
                    StartWorker();
                    _logger.LogInformation("Autoscaler: UP -> workers={Count}, backlog={Depth}, mem={MemMB}MB",
                        _workerCts.Count, depth, mem / (1024 * 1024));
                }
                // Scale down
                else if ((depth < _scaleDownBacklog || mem > _maxRamBytes) && _workerCts.Count > _minWorkers)
                {
                    StopOneWorker();
                    _logger.LogInformation("Autoscaler: DOWN -> workers={Count}, backlog={Depth}, mem={MemMB}MB",
                        _workerCts.Count, depth, mem / (1024 * 1024));
                }
            }
            catch (Exception ex)
            {
                _logger.LogDebug(ex, "Autoscaler tick error");
            }

            await Task.Delay(500, _cts.Token);
        }
    }

    private async Task WorkerLoopAsync(CancellationToken token)
    {
        ISender? sender = null;
        try
        {
            sender = Sender.New(_connectionString);
            var reader = _packetChannel.Reader;
            var batch = new List<PacketData>(_options.BatchSize);

            while (!token.IsCancellationRequested)
            {
                // Block for first item
                var first = await reader.ReadAsync(token);
                batch.Clear();
                batch.Add(first);

                // Drain up to BatchSize or until timeout
                var deadline = DateTime.UtcNow.AddMilliseconds(_options.BatchTimeoutMs);
                while (batch.Count < _options.BatchSize)
                {
                    while (reader.TryRead(out var item))
                    {
                        batch.Add(item);
                        if (batch.Count >= _options.BatchSize) break;
                    }

                    if (batch.Count >= _options.BatchSize || DateTime.UtcNow >= deadline) break;
                    await Task.Delay(1, token);
                }

                // We’re about to consume these items from backlog
                Interlocked.Add(ref _queuedCount, -batch.Count);

                // Write one batch on this sender
                await WriteBatch(sender, batch);
            }
        }
        catch (OperationCanceledException) { /* shutting down */ }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Worker crashed; restarting in 500ms");
            await Task.Delay(500, token);
            if (!token.IsCancellationRequested) _ = Task.Run(() => WorkerLoopAsync(token), token);
        }
        finally
        {
            try { sender?.Dispose(); } catch { /* ignore */ }
        }
    }

    private async Task WriteBatch(ISender sender, List<PacketData> batch)
    {
        // Sort by timestamp to help O3
        batch.Sort((a, b) =>
        {
            var cmp = a.Timestamp.CompareTo(b.Timestamp);
            return cmp != 0 ? cmp : a.Id.CompareTo(b.Id);
        });

        try
        {
            foreach (var p in batch)
            {
                var ts = p.Timestamp == default ? DateTime.UtcNow : p.Timestamp;

                await sender.Table("packets")
                      .Symbol("protocol", p.Protocol ?? string.Empty)
                      .Symbol("device_name", p.DeviceName ?? string.Empty)
                      .Column("id", p.Id.ToString())
                      .Column("source_ip", p.SourceIp ?? string.Empty)
                      .Column("destination_ip", p.DestinationIp ?? string.Empty)
                      .Column("source_port", p.SourcePort)
                      .Column("destination_port", p.DestinationPort)
                      .Column("length", p.Length)
                      .AtAsync(ts);
            }
            // rely on auto-flush in Sender (rows+interval); no explicit Flush
        }
        catch (Exception ex) when (ex is IOException || ex is SocketException || ex.GetType().Name.Contains("Ingress"))
        {
            // Recreate connection and retry once
            _logger.LogWarning(ex, "ILP write failed in worker; recreating sender and retrying batch once...");
            try { sender.Dispose(); } catch { /* ignore */ }
            sender = Sender.New(_connectionString);

            foreach (var p in batch)
            {
                var ts = p.Timestamp == default ? DateTime.UtcNow : p.Timestamp;

                await sender.Table("packets")
                      .Symbol("protocol", p.Protocol ?? string.Empty)
                      .Symbol("device_name", p.DeviceName ?? string.Empty)
                      .Column("id", p.Id.ToString())
                      .Column("source_ip", p.SourceIp ?? string.Empty)
                      .Column("destination_ip", p.DestinationIp ?? string.Empty)
                      .Column("source_port", p.SourcePort)
                      .Column("destination_port", p.DestinationPort)
                      .Column("length", p.Length)
                      .AtAsync(ts);
            }
        }
    }

    // Cleanup ------------------------------------------------------------------

    public void Dispose()
    {
        _cts.Cancel();

        foreach (var cts in _workerCts)
            cts.Cancel();

        try { Task.WaitAll([.. _workerTasks], TimeSpan.FromSeconds(3)); } catch { /* ignore */ }

        _workerCts.Clear();
        _workerTasks.Clear();
        _cts.Dispose();
    }
}
