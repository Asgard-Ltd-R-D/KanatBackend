namespace PacketProcessing.Services.Networking;

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using PacketProcessing.Entities;
using PacketProcessing.Utils.Parsers;

public class CaptureService<T> : BackgroundService, IObserver<RawPacketEvent>, IObservable<T>
    where T : BasePacketEntity
{
    private readonly ILogger<CaptureService<T>> _logger;
    private readonly Channel<T> _channel;
    private readonly DeviceManager _deviceManager;

    // Config used for filtering (if you later add header filtering)
    private readonly string _protocol;
    private readonly IReadOnlyList<string> _ips;

    // State
    private bool _isCapturing;
    private readonly object _captureLock = new();

    // Observers (built-in pattern)
    private readonly List<IObserver<T>> _observers = new();
    private readonly object _observersLock = new();

    // Perf counters
    private long _packetsProcessed;
    private long _packetsDropped;
    private long _packetsCaptured;

    public CaptureService(
        ILogger<CaptureService<T>> logger,
        IConfiguration configuration,
        Channel<T> channel,
        string dataPipeName,
        DeviceManager deviceManager)
    {
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _channel = channel ?? throw new ArgumentNullException(nameof(channel));
        _deviceManager = deviceManager ?? throw new ArgumentNullException(nameof(deviceManager));

        var networkSection = configuration.GetSection("DataPipes").GetSection(dataPipeName).GetSection("Network");
        _protocol = networkSection.GetValue<string>("Protocol") ?? "tcp";
        _ips = networkSection.GetSection("IPs").Get<string[]>() ?? Array.Empty<string>();

        // Subscribe to the shared publisher of raw packets
        _deviceManager.Subscribe(this);
    }

    #region IObservable<T> (producer of parsed packets)

    public IDisposable Subscribe(IObserver<T> observer)
    {
        if (observer == null) throw new ArgumentNullException(nameof(observer));
        lock (_observersLock)
        {
            if (!_observers.Contains(observer))
                _observers.Add(observer);
        }
        return new Unsubscriber<T>(_observers, observer, _observersLock);
    }

    private sealed class Unsubscriber<TObs> : IDisposable
    {
        private readonly List<IObserver<TObs>> _observers;
        private readonly IObserver<TObs> _observer;
        private readonly object _lock;

        public Unsubscriber(List<IObserver<TObs>> observers, IObserver<TObs> observer, object lck)
        {
            _observers = observers;
            _observer = observer;
            _lock = lck;
        }

        public void Dispose()
        {
            lock (_lock)
            {
                if (_observers.Contains(_observer))
                    _observers.Remove(_observer);
            }
        }
    }

    private void NotifyObserversNext(T packet)
    {
        List<IObserver<T>> snapshot;
        lock (_observersLock) snapshot = _observers.ToList();

        foreach (var o in snapshot)
        {
            try { o.OnNext(packet); }
            catch (Exception ex) { _logger.LogError(ex, "Observer threw during OnNext"); }
        }
    }

    private void NotifyObserversError(Exception error)
    {
        List<IObserver<T>> snapshot;
        lock (_observersLock) snapshot = _observers.ToList();

        foreach (var o in snapshot)
        {
            try { o.OnError(error); } catch { /* ignore */ }
        }
    }

    private void NotifyObserversCompleted()
    {
        List<IObserver<T>> snapshot;
        lock (_observersLock) snapshot = _observers.ToList();

        foreach (var o in snapshot)
        {
            try { o.OnCompleted(); } catch { /* ignore */ }
        }
    }

    #endregion

    #region IObserver<RawPacketEvent> (consumer of raw packets)

    public void OnNext(RawPacketEvent evt)
    {
        var captured = Interlocked.Increment(ref _packetsCaptured);

        try
        {
            // TODO: If you want, add fast header filtering by _protocol/_ips here before parsing.

            var parsed = ParsePacket(evt.Data.Span);
            if (parsed is null)
            {
                Interlocked.Increment(ref _packetsDropped);
                return;
            }

            var vt = HandlePacket(parsed);
            if (vt.IsCompletedSuccessfully)
            {
                Interlocked.Increment(ref _packetsProcessed);
            }
            else
            {
                _ = vt.AsTask().ContinueWith(t =>
                {
                    if (t.IsFaulted)
                    {
                        Interlocked.Increment(ref _packetsDropped);
                        _logger.LogError(t.Exception, "Packet write failed");
                        NotifyObserversError(t.Exception!);
                    }
                    else
                    {
                        Interlocked.Increment(ref _packetsProcessed);
                    }
                }, TaskScheduler.Default);
            }

            NotifyObserversNext(parsed);
        }
        catch (Exception ex)
        {
            Interlocked.Increment(ref _packetsDropped);
            _logger.LogError(ex, "Exception handling RawPacketEvent");
            NotifyObserversError(ex);
        }
        finally
        {
            LogPacketStatsIfNeeded(captured);
        }
    }

    public void OnError(Exception error)
    {
        _logger.LogError(error, "DeviceManager signaled error");
        NotifyObserversError(error);
    }

    public void OnCompleted()
    {
        _logger.LogInformation("DeviceManager completed");
        NotifyObserversCompleted();
    }

    #endregion

    #region Public capture control (delegates to DeviceManager)

    // Keep these so existing code (Motion/Safety/OnVIF services) continues to compile.
    public Task StartCaptureAsync()
    {
        lock (_captureLock)
        {
            if (_isCapturing) return Task.CompletedTask;
            _isCapturing = true;
        }

        _logger.LogInformation("Starting shared capture via DeviceManager");
        _deviceManager.StartAll();
        return Task.CompletedTask;
    }

    public Task StopCaptureAsync()
    {
        lock (_captureLock)
        {
            if (!_isCapturing) return Task.CompletedTask;
            _isCapturing = false;
        }

        _logger.LogInformation("Stopping shared capture via DeviceManager");
        _deviceManager.StopAll();

        // reset counters
        Interlocked.Exchange(ref _packetsCaptured, 0);
        Interlocked.Exchange(ref _packetsProcessed, 0);
        Interlocked.Exchange(ref _packetsDropped, 0);

        return Task.CompletedTask;
    }

    public bool IsCapturing => _isCapturing;

    #endregion

    #region Parse & write

    public T ParsePacket(ReadOnlySpan<byte> rawPacket)
    {
        if (rawPacket.IsEmpty) return null!;
        var packet = ParseMapper.Map<T>(rawPacket);
        return packet!;
    }

    internal ValueTask HandlePacket(T packet)
    {
        if (packet is null) return default;
        return _channel.Writer.WriteAsync(packet);
    }

    #endregion

    #region Infra

    protected override Task ExecuteAsync(CancellationToken stoppingToken)
    {
        // Nothing to do here; DeviceManager drives OnNext.
        return Task.CompletedTask;
    }

    private void LogPacketStatsIfNeeded(long captured)
    {
        var processed = Interlocked.Read(ref _packetsProcessed);
        if ((processed > 0 && processed % 100 == 0) || (processed == 0 && captured > 0 && captured % 1000 == 0))
        {
            var dropped = Interlocked.Read(ref _packetsDropped);
            var successRate = captured > 0 ? (double)processed / captured : 0.0;
            _logger.LogInformation(
                "Capture Stats: Captured {Captured}, Processed {Processed}, Dropped {Dropped}, Success {Success:P1}",
                captured, processed, dropped, successRate);
        }
    }

    public override void Dispose()
    {
        try
        {
            // Keep this so previous behavior remains: stop capture on dispose.
            StopCaptureAsync().Wait();
            GC.SuppressFinalize(this);
        }
        catch { /* best-effort */ }

        base.Dispose();
    }

    #endregion
}
