using System.Threading.Channels;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using PacketProcessing.Entities;
using PacketProcessing.Utils.Parsers;
using PacketProcessing.Utils.Filters;
using PacketProcessing.Config;
using System.Runtime.InteropServices;
using System.Buffers;

namespace PacketProcessing.Services.Networking;

public class HandlerService<T> : BackgroundService, IHandlerService<T>, IObserver<RawPacketEvent>
    where T : BasePacketEntity
{
    private readonly ILogger<HandlerService<T>> _logger;

    // Device filters
    private readonly string _protocol;
    private readonly IEnumerable<string> _ips;

    // Channels
    private readonly Channel<RawPacketEvent> _rawChannel; // device -> handler
    private readonly Channel<T> _parsedChannel;           // handler -> DbWriter

    private readonly int _workerCount;

    // Stats
    private long _packetsCaptured;
    private long _packetsParsed;
    private long _packetsDropped;
    private long _backpressureEvents;

    private const int RAW_READ_BURST = 64; // Smaller burst for lower latency

    private IDisposable? _subscription;

    public HandlerService(
        string dataPipeName,
        ILogger<HandlerService<T>> logger,
        Channel<T> parsedChannel,
        IConfiguration configuration)
    {
        _logger = logger;
        _parsedChannel = parsedChannel;

        // bounded channel for raw events with increased capacity
        // Wait mode ensures no packets are dropped (capture may block if processing too slow)
        _rawChannel = Channel.CreateBounded<RawPacketEvent>(
            new BoundedChannelOptions(500_000) { 
                SingleReader = false,  // Multiple workers read
                SingleWriter = false,  // DeviceService may write from multiple threads via Task.Run
                FullMode = BoundedChannelFullMode.Wait  // Block to guarantee delivery
            });

        _protocol = configuration.GetValue<string>($"{dataPipeName}:Network:Protocol") ?? "";
        _ips = configuration.GetSection($"{dataPipeName}:Network:IPs").Get<IEnumerable<string>>() ?? [];

        var concurrency = configuration.GetSection("Concurrency");
        var min = concurrency.GetValue<int>("MinWorkers", 2);
        var max = concurrency.GetValue<int>("MaxWorkers", 8);
        _workerCount = Math.Clamp(Environment.ProcessorCount, min, max);

        _logger.LogInformation(
            "{Handler} initialized with {Workers} workers",
            typeof(T).Name, _workerCount);
    }

    #region IHandlerService

    public async Task SubscribeToDeviceAsync(IDeviceService deviceService, string deviceName)
    {
        var filter = BpfFilterBuilder.Build(_protocol, _ips);
        await deviceService.SubscribeWithFilterAsync(this, deviceName, filter);
        _logger.LogInformation("{Handler} subscribed to {Device} with filter {Filter}",
            typeof(T).Name, deviceName, filter);
    }

    public async Task UnsubscribeAsync(IDeviceService deviceService)
    {
        _subscription?.Dispose();
        _subscription = null;
        await deviceService.UnsubscribeAsync(this);

        Interlocked.Exchange(ref _packetsCaptured, 0);
        Interlocked.Exchange(ref _packetsParsed, 0);
        Interlocked.Exchange(ref _packetsDropped, 0);
        Interlocked.Exchange(ref _backpressureEvents, 0);

        _logger.LogInformation("{Handler} unsubscribed", typeof(T).Name);
    }

    public (long Captured, long Parsed, long Dropped) GetStats() =>
        (Interlocked.Read(ref _packetsCaptured),
         Interlocked.Read(ref _packetsParsed),
         Interlocked.Read(ref _packetsDropped));
    
    public long GetBackpressureEvents() => Interlocked.Read(ref _backpressureEvents);

    #endregion

    #region IObserver<RawPacketEvent>

    public void OnNext(RawPacketEvent evt)
    {
        Interlocked.Increment(ref _packetsCaptured);

        // Try fast path first
        if (_rawChannel.Writer.TryWrite(evt))
            return;

        // Channel full - Wait mode will block to guarantee delivery
        Interlocked.Increment(ref _backpressureEvents);
        
        // This blocks until space available (guarantees packet is written)
        _rawChannel.Writer
            .WriteAsync(evt, CancellationToken.None)
            .AsTask()
            .GetAwaiter()
            .GetResult();
    }

    public void OnError(Exception error) =>
        _logger.LogError(error, "Device service signaled error");

    public void OnCompleted()
    {
        _logger.LogInformation("Device service completed");
        _rawChannel.Writer.Complete();
    }

    #endregion

    #region BackgroundService

    protected override Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var workers = Enumerable.Range(0, _workerCount)
            .Select(i => Task.Factory.StartNew(
                () => WorkerLoopAsync(i, stoppingToken),
                stoppingToken,
                TaskCreationOptions.LongRunning,
                TaskScheduler.Default).Unwrap())
            .ToArray();

        return Task.WhenAll(workers);
    }

    private async Task WorkerLoopAsync(int workerId, CancellationToken token)
    {
        // Reuse buffers to avoid per-iteration allocs
        var rawBatch = new List<RawPacketEvent>(RAW_READ_BURST);
        
        try
        {
            while (!token.IsCancellationRequested)
            {
                rawBatch.Clear();
                int batchParsed = 0;
                int batchDropped = 0;
                int batchBackpressure = 0;

                // ---- 1) Block for first item (start a mini-batch) ----
                RawPacketEvent first;
                try
                {
                    first = await _rawChannel.Reader.ReadAsync(token);
                }
                catch (ChannelClosedException)
                {
                    break; // upstream completed
                }
                rawBatch.Add(first);

                // ---- 2) Aggressively drain what's immediately available ----
                while (rawBatch.Count < RAW_READ_BURST && _rawChannel.Reader.TryRead(out var more))
                    rawBatch.Add(more);

                // ---- 3) Parse and forward ----
                DateTime? firstParsedTimestamp = null;
                DateTime? lastParsedTimestamp = null;
                
                for (int i = 0; i < rawBatch.Count; i++)
                {
                    var raw = rawBatch[i];
                    ArraySegment<byte> segment = default;
                    try
                    {
                        var parsed = Parse(raw.Data.Span);

                        if (parsed is null)
                        {
                            Interlocked.Increment(ref _packetsDropped);
                            batchDropped++;
                            continue;
                        }

                        // Track timestamps for latency measurement
                        if (firstParsedTimestamp == null)
                            firstParsedTimestamp = parsed.Timestamp;
                        lastParsedTimestamp = parsed.Timestamp;

                        // Try fast path to parsed channel; otherwise await (true backpressure)
                        if (!_parsedChannel.Writer.TryWrite(parsed))
                        {
                            Interlocked.Increment(ref _backpressureEvents);
                            batchBackpressure++;
                            await _parsedChannel.Writer.WriteAsync(parsed, token);
                        }

                        Interlocked.Increment(ref _packetsParsed);
                        batchParsed++;
                    }
                    catch
                    {
                        Interlocked.Increment(ref _packetsDropped);
                        batchDropped++;
                    }
                    finally
                    {
                        // Return pooled memory *after* processing is done
                        if (MemoryMarshal.TryGetArray(raw.Data, out segment) && segment.Array is not null)
                            ArrayPool<byte>.Shared.Return(segment.Array);
                    }
                }

                // ---- 4) Log every parsing batch with stats ----
                var totalCaptured = Interlocked.Read(ref _packetsCaptured);
                var totalParsed = Interlocked.Read(ref _packetsParsed);
                var totalDropped = Interlocked.Read(ref _packetsDropped);
                var totalBackpressure = Interlocked.Read(ref _backpressureEvents);
                
                // Calculate parsing latency from this batch
                var parsingLatencyMs = 0.0;
                if (batchParsed > 0 && lastParsedTimestamp.HasValue)
                {
                    // Measure actual time from packet creation to being sent to DB writer
                    parsingLatencyMs = (DateTime.UtcNow - lastParsedTimestamp.Value).TotalMilliseconds;
                }
                
                _logger.LogInformation(
                    "[PARSER] {Entity} Worker {Worker}: Batch=(Parsed:{BatchParsed} Dropped:{BatchDropped} BP:{BatchBP} Latency:{Latency:F1}ms) Total=(Captured:{TotalCaptured} Parsed:{TotalParsed} Dropped:{TotalDropped} BP:{TotalBP})",
                    typeof(T).Name, workerId, batchParsed, batchDropped, batchBackpressure, parsingLatencyMs, totalCaptured, totalParsed, totalDropped, totalBackpressure);
            }
        }

        catch (OperationCanceledException) { }
    }

    #endregion

    private static T? Parse(ReadOnlySpan<byte> raw)
    {
        if (raw.IsEmpty) return null;
        try { return ParseMapper.Map<T>(raw); }
        catch { return null; }
    }
}
