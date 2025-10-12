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

    private const int RAW_READ_BURST = 256; // tune: 128–512
    private const int LOG_PERIOD_MS = 10_000;

    private IDisposable? _subscription;

    public HandlerService(
        string dataPipeName,
        ILogger<HandlerService<T>> logger,
        Channel<T> parsedChannel,
        IConfiguration configuration)
    {
        _logger = logger;
        _parsedChannel = parsedChannel;

        // bounded channel for raw events with increased capacity and backpressure
        _rawChannel = Channel.CreateBounded<RawPacketEvent>(
            new BoundedChannelOptions(500_000) { 
                SingleReader = false,  // Multiple workers read
                SingleWriter = false,  // DeviceService may write from multiple threads via Task.Run
                FullMode = BoundedChannelFullMode.Wait 
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

        // Try fast path
        if (_rawChannel.Writer.TryWrite(evt))
            return;

        // Channel is full: block and *actually* apply backpressure
        // Count a backpressure event so you can observe hot spots
        Interlocked.Increment(ref _backpressureEvents);

        // This must synchronously wait here to *guarantee* enqueue
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
        var sw = System.Diagnostics.Stopwatch.StartNew();
        long lastLogMs = sw.ElapsedMilliseconds;

        // Reuse buffers to avoid per-iteration allocs
        var rawBatch = new List<RawPacketEvent>(RAW_READ_BURST);

        try
        {
            while (!token.IsCancellationRequested)
            {
                rawBatch.Clear();

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

                // ---- 3) Soft-wait fill until a short deadline to gather a few more ----
                // This keeps latency low when traffic is sparse, but boosts throughput under load.
                var deadlineMs = sw.ElapsedMilliseconds + 2; // tune: 1–5ms micro-batch window
                while (rawBatch.Count < RAW_READ_BURST)
                {
                    var remaining = (int)(deadlineMs - sw.ElapsedMilliseconds);
                    if (remaining <= 0) break;

                    var readTask = _rawChannel.Reader.ReadAsync(token).AsTask();
                    var delayTask = Task.Delay(remaining, token);
                    var completed = await Task.WhenAny(readTask, delayTask);
                    if (completed == readTask)
                    {
                        rawBatch.Add(readTask.Result);
                        while (rawBatch.Count < RAW_READ_BURST && _rawChannel.Reader.TryRead(out var add))
                            rawBatch.Add(add);
                    }
                    else
                    {
                        break; // deadline reached
                    }
                }

                // ---- 4) Parse and forward ----
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
                            continue;
                        }

                        // Try fast path to parsed channel; otherwise await (true backpressure)
                        if (!_parsedChannel.Writer.TryWrite(parsed))
                        {
                            parsed.Timestamp = raw.Timestamp; // Override the timestamp to the actual timestamp of the packet
                            Interlocked.Increment(ref _backpressureEvents);
                            await _parsedChannel.Writer.WriteAsync(parsed, token);
                        }

                        Interlocked.Increment(ref _packetsParsed);
                    }
                    catch
                    {
                        Interlocked.Increment(ref _packetsDropped);
                    }
                    finally
                    {
                        // Return pooled memory *after* processing is done
                        if (MemoryMarshal.TryGetArray(raw.Data, out segment) && segment.Array is not null)
                            ArrayPool<byte>.Shared.Return(segment.Array);
                    }
                }

                // ---- 5) Non-blocking periodic log ----
                var nowMs = sw.ElapsedMilliseconds;
                if (nowMs - lastLogMs >= LOG_PERIOD_MS)
                {
                    var cap = Interlocked.Read(ref _packetsCaptured);
                    var par = Interlocked.Read(ref _packetsParsed);
                    var drp = Interlocked.Read(ref _packetsDropped);
                    var bp  = Interlocked.Read(ref _backpressureEvents);
                    _logger.LogInformation(
                        "[{Entity}] Worker {Worker} Captured={Captured} Parsed={Parsed} Dropped={Dropped} BP={Backpressure}",
                        typeof(T).Name, workerId, cap, par, drp, bp);
                    lastLogMs = nowMs;
                }
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
