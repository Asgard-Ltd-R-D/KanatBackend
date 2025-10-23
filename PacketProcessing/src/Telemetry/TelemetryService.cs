using System.Collections.Concurrent;
using PacketProcessing.DTOs;

namespace PacketProcessing.Telemetry;

/// <summary>
/// Thread-safe implementation of telemetry data collection service
/// </summary>
public class TelemetryService : ITelemetryService
{
    private readonly ConcurrentDictionary<string, ChannelStatsDto> _channelStats = new();
    private readonly TelemetryBroadcaster? _broadcaster;
    private long _captured = 0;
    private long _parsed = 0;
    private long _dropped = 0;
    private long _flushed = 0;
    private long _failed = 0;
    private long _backpressure = 0;
    private double _avgLatency = 0;
    private long _motionCaptured = 0;
    private long _safetyCaptured = 0;
    private long _onvifCaptured = 0;
    private long _totalLatency = 0;
    private long _latencyCount = 0;
    
    // Change tracking
    private volatile bool _hasChanges = false;

    public TelemetryService(TelemetryBroadcaster? broadcaster = null)
    {
        _broadcaster = broadcaster;
    }

    public Task<TelemetryDto> SnapshotAsync()
    {
        var snapshot = new TelemetryDto
        {
            Captured = Interlocked.Read(ref _captured),
            Parsed = Interlocked.Read(ref _parsed),
            Dropped = Interlocked.Read(ref _dropped),
            Flushed = Interlocked.Read(ref _flushed),
            Failed = Interlocked.Read(ref _failed),
            Backpressure = Interlocked.Read(ref _backpressure),
            AvgLatency = _avgLatency,
            MotionCaptured = Interlocked.Read(ref _motionCaptured),
            SafetyCaptured = Interlocked.Read(ref _safetyCaptured),
            OnvifCaptured = Interlocked.Read(ref _onvifCaptured),
            MotionRawChannel = GetChannelStats("MotionRaw"),
            SafetyRawChannel = GetChannelStats("SafetyRaw"),
            OnvifRawChannel = GetChannelStats("OnvifRaw"),
            MotionParsedChannel = GetChannelStats("MotionParsed"),
            SafetyParsedChannel = GetChannelStats("SafetyParsed"),
            OnvifParsedChannel = GetChannelStats("OnvifParsed")
        };

        return Task.FromResult(snapshot);
    }

    public bool HasChanges()
    {
        return _hasChanges;
    }

    public void MarkSnapshotTaken()
    {
        _hasChanges = false;
    }

    public void IncrementCaptured(long count = 1)
    {
        Interlocked.Add(ref _captured, count);
        _hasChanges = true;
        _broadcaster?.NotifyChange();
    }

    public void IncrementParsed(long count = 1)
    {
        Interlocked.Add(ref _parsed, count);
        _hasChanges = true;
        _broadcaster?.NotifyChange();
    }

    public void IncrementDropped(long count = 1)
    {
        Interlocked.Add(ref _dropped, count);
        _hasChanges = true;
        _broadcaster?.NotifyChange();
    }

    public void IncrementFlushed(long count = 1)
    {
        Interlocked.Add(ref _flushed, count);
        _hasChanges = true;
        _broadcaster?.NotifyChange();
    }

    public void IncrementFailed(long count = 1)
    {
        Interlocked.Add(ref _failed, count);
        _hasChanges = true;
        _broadcaster?.NotifyChange();
    }

    public void IncrementBackpressure(long count = 1)
    {
        Interlocked.Add(ref _backpressure, count);
        _hasChanges = true;
        _broadcaster?.NotifyChange();
    }

    public void UpdateLatency(double latency)
    {
        Interlocked.Add(ref _totalLatency, (long)(latency * 1000)); // Convert to microseconds for precision
        Interlocked.Increment(ref _latencyCount);
        
        var totalLatency = Interlocked.Read(ref _totalLatency);
        var latencyCount = Interlocked.Read(ref _latencyCount);
        
        if (latencyCount > 0)
        {
            _avgLatency = totalLatency / (double)latencyCount / 1000.0; // Convert back to milliseconds
        }
        _hasChanges = true;
        _broadcaster?.NotifyChange();
    }

    public void IncrementMotionCaptured(long count = 1)
    {
        Interlocked.Add(ref _motionCaptured, count);
        _hasChanges = true;
        _broadcaster?.NotifyChange();
    }

    public void IncrementSafetyCaptured(long count = 1)
    {
        Interlocked.Add(ref _safetyCaptured, count);
        _hasChanges = true;
        _broadcaster?.NotifyChange();
    }

    public void IncrementOnvifCaptured(long count = 1)
    {
        Interlocked.Add(ref _onvifCaptured, count);
        _hasChanges = true;
        _broadcaster?.NotifyChange();
    }

    public void UpdateChannelStats(string channelName, int capacity, int currentSize, double utilizationPercent)
    {
        var channelStats = new ChannelStatsDto
        {
            Capacity = capacity,
            CurrentSize = currentSize,
            UtilizationPercent = utilizationPercent
        };
        
        _channelStats.AddOrUpdate(channelName, channelStats, (key, oldValue) => channelStats);
        _hasChanges = true;
        _broadcaster?.NotifyChange();
    }

    public void Reset()
    {
        Interlocked.Exchange(ref _captured, 0);
        Interlocked.Exchange(ref _parsed, 0);
        Interlocked.Exchange(ref _dropped, 0);
        Interlocked.Exchange(ref _flushed, 0);
        Interlocked.Exchange(ref _failed, 0);
        Interlocked.Exchange(ref _backpressure, 0);
        Interlocked.Exchange(ref _motionCaptured, 0);
        Interlocked.Exchange(ref _safetyCaptured, 0);
        Interlocked.Exchange(ref _onvifCaptured, 0);
        Interlocked.Exchange(ref _totalLatency, 0);
        Interlocked.Exchange(ref _latencyCount, 0);
        _avgLatency = 0;
        
        _channelStats.Clear();
        _hasChanges = true;
        _broadcaster?.NotifyChange();
    }

    public void SetTestData()
    {
        Interlocked.Exchange(ref _captured, 1000);
        Interlocked.Exchange(ref _parsed, 950);
        Interlocked.Exchange(ref _dropped, 25);
        Interlocked.Exchange(ref _flushed, 925);
        Interlocked.Exchange(ref _failed, 5);
        Interlocked.Exchange(ref _backpressure, 10);
        Interlocked.Exchange(ref _motionCaptured, 400);
        Interlocked.Exchange(ref _safetyCaptured, 350);
        Interlocked.Exchange(ref _onvifCaptured, 250);
        Interlocked.Exchange(ref _totalLatency, 5000);
        Interlocked.Exchange(ref _latencyCount, 100);
        _avgLatency = 5.0;
        
        _hasChanges = true;
        _broadcaster?.NotifyChange();
    }

    private ChannelStatsDto? GetChannelStats(string channelName)
    {
        return _channelStats.TryGetValue(channelName, out var stats) ? stats : null;
    }
}
