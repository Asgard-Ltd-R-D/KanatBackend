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
            new BoundedChannelOptions(500_000) { SingleReader = false, SingleWriter = true, FullMode = BoundedChannelFullMode.Wait });

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

        _logger.LogInformation("{Handler} unsubscribed", typeof(T).Name);
    }

    public (long Captured, long Parsed, long Dropped) GetStats() =>
        (Interlocked.Read(ref _packetsCaptured),
         Interlocked.Read(ref _packetsParsed),
         Interlocked.Read(ref _packetsDropped));

    #endregion

    #region IObserver<RawPacketEvent>

    public void OnNext(RawPacketEvent evt)
    {
        Interlocked.Increment(ref _packetsCaptured);

        // Block if channel is full (backpressure to capture)
        if (!_rawChannel.Writer.TryWrite(evt))
        {
            _rawChannel.Writer.WriteAsync(evt).AsTask().GetAwaiter().GetResult();
        }
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
        try
        {
            await foreach (var raw in _rawChannel.Reader.ReadAllAsync(token))
            {
                ArraySegment<byte> segment = default;
                try
                {
                    var parsed = Parse(raw.Data.Span);

                    if (parsed is null)
                    {
                        Interlocked.Increment(ref _packetsDropped);
                    }
                    else
                    {
                        // Apply backpressure if channel is full
                        if (!_parsedChannel.Writer.TryWrite(parsed))
                        {
                            await _parsedChannel.Writer.WriteAsync(parsed, token);
                        }
                        Interlocked.Increment(ref _packetsParsed);
                    }
                }
                catch (Exception ex)
                {
                    Interlocked.Increment(ref _packetsDropped);
                    _logger.LogError(ex, "Worker {Worker} failed to parse packet", workerId);
                }
                finally
                {
                    // Return pooled memory after all processing is complete
                    if (MemoryMarshal.TryGetArray(raw.Data, out segment))
                        ArrayPool<byte>.Shared.Return(segment.Array!);
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
