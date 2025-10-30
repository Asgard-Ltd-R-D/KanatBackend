using System.Collections.Concurrent;
using PacketProcessing.DTOs;

namespace PacketProcessing.Telemetry;

/// <summary>
/// Thread-safe implementation of telemetry data collection service
/// </summary>
public class TelemetryService : ITelemetryService
{
    private readonly ConcurrentDictionary<string, ChannelStatsDto> _channelStats = new();
    private readonly ConcurrentDictionary<string, ChannelLatencyTracker> _channelLatencyTrackers = new();
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
    private long _motionCaptureFail = 0;
    private long _safetyCaptureFail = 0;
    private long _onvifCaptureFail = 0;

    // Per-entity parse
    private long _motionParseSuccess = 0;
    private long _motionParseFail = 0;
    private long _safetyParseSuccess = 0;
    private long _safetyParseFail = 0;
    private long _onvifParseSuccess = 0;
    private long _onvifParseFail = 0;

    // Per-entity flush
    private long _motionFlushSuccess = 0;
    private long _motionFlushFail = 0;
    private long _safetyFlushSuccess = 0;
    private long _safetyFlushFail = 0;
    private long _onvifFlushSuccess = 0;
    private long _onvifFlushFail = 0;
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
            // Per-entity capture fail
            MotionCaptureFail = Interlocked.Read(ref _motionCaptureFail),
            SafetyCaptureFail = Interlocked.Read(ref _safetyCaptureFail),
            OnvifCaptureFail = Interlocked.Read(ref _onvifCaptureFail),
            // Per-entity parse
            MotionParseSuccess = Interlocked.Read(ref _motionParseSuccess),
            MotionParseFail = Interlocked.Read(ref _motionParseFail),
            SafetyParseSuccess = Interlocked.Read(ref _safetyParseSuccess),
            SafetyParseFail = Interlocked.Read(ref _safetyParseFail),
            OnvifParseSuccess = Interlocked.Read(ref _onvifParseSuccess),
            OnvifParseFail = Interlocked.Read(ref _onvifParseFail),
            // Per-entity flush
            MotionFlushSuccess = Interlocked.Read(ref _motionFlushSuccess),
            MotionFlushFail = Interlocked.Read(ref _motionFlushFail),
            SafetyFlushSuccess = Interlocked.Read(ref _safetyFlushSuccess),
            SafetyFlushFail = Interlocked.Read(ref _safetyFlushFail),
            OnvifFlushSuccess = Interlocked.Read(ref _onvifFlushSuccess),
            OnvifFlushFail = Interlocked.Read(ref _onvifFlushFail),
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

    public void IncrementMotionCaptureFail(long count = 1) { Interlocked.Add(ref _motionCaptureFail, count); _hasChanges = true; _broadcaster?.NotifyChange(); }
    public void IncrementSafetyCaptureFail(long count = 1) { Interlocked.Add(ref _safetyCaptureFail, count); _hasChanges = true; _broadcaster?.NotifyChange(); }
    public void IncrementOnvifCaptureFail(long count = 1) { Interlocked.Add(ref _onvifCaptureFail, count); _hasChanges = true; _broadcaster?.NotifyChange(); }

    public void IncrementMotionParseSuccess(long count = 1) { Interlocked.Add(ref _motionParseSuccess, count); _hasChanges = true; _broadcaster?.NotifyChange(); }
    public void IncrementMotionParseFail(long count = 1) { Interlocked.Add(ref _motionParseFail, count); _hasChanges = true; _broadcaster?.NotifyChange(); }
    public void IncrementSafetyParseSuccess(long count = 1) { Interlocked.Add(ref _safetyParseSuccess, count); _hasChanges = true; _broadcaster?.NotifyChange(); }
    public void IncrementSafetyParseFail(long count = 1) { Interlocked.Add(ref _safetyParseFail, count); _hasChanges = true; _broadcaster?.NotifyChange(); }
    public void IncrementOnvifParseSuccess(long count = 1) { Interlocked.Add(ref _onvifParseSuccess, count); _hasChanges = true; _broadcaster?.NotifyChange(); }
    public void IncrementOnvifParseFail(long count = 1) { Interlocked.Add(ref _onvifParseFail, count); _hasChanges = true; _broadcaster?.NotifyChange(); }

    public void IncrementMotionFlushSuccess(long count = 1) { Interlocked.Add(ref _motionFlushSuccess, count); _hasChanges = true; _broadcaster?.NotifyChange(); }
    public void IncrementMotionFlushFail(long count = 1) { Interlocked.Add(ref _motionFlushFail, count); _hasChanges = true; _broadcaster?.NotifyChange(); }
    public void IncrementSafetyFlushSuccess(long count = 1) { Interlocked.Add(ref _safetyFlushSuccess, count); _hasChanges = true; _broadcaster?.NotifyChange(); }
    public void IncrementSafetyFlushFail(long count = 1) { Interlocked.Add(ref _safetyFlushFail, count); _hasChanges = true; _broadcaster?.NotifyChange(); }
    public void IncrementOnvifFlushSuccess(long count = 1) { Interlocked.Add(ref _onvifFlushSuccess, count); _hasChanges = true; _broadcaster?.NotifyChange(); }
    public void IncrementOnvifFlushFail(long count = 1) { Interlocked.Add(ref _onvifFlushFail, count); _hasChanges = true; _broadcaster?.NotifyChange(); }

    public void UpdateChannelStats(string channelName, int capacity, int currentSize, double utilizationPercent, int workers = 0, double avgLatencyMs = 0)
    {
        var tracker = _channelLatencyTrackers.GetOrAdd(channelName, _ => new ChannelLatencyTracker());
        var avgLatency = tracker.GetAverageLatency();
        
        var channelStats = new ChannelStatsDto
        {
            Capacity = capacity,
            CurrentSize = currentSize,
            UtilizationPercent = utilizationPercent,
            Workers = workers,
            AvgLatencyMs = avgLatencyMs
        };
        
        _channelStats.AddOrUpdate(channelName, channelStats, (key, oldValue) => channelStats);
        _hasChanges = true;
        _broadcaster?.NotifyChange();
    }

    public void AddChannelLatency(string channelName, double latencyMs)
    {
        var tracker = _channelLatencyTrackers.GetOrAdd(channelName, _ => new ChannelLatencyTracker());
        tracker.AddLatency(latencyMs);
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
        Interlocked.Exchange(ref _motionCaptureFail, 0);
        Interlocked.Exchange(ref _safetyCaptureFail, 0);
        Interlocked.Exchange(ref _onvifCaptureFail, 0);
        Interlocked.Exchange(ref _motionParseSuccess, 0);
        Interlocked.Exchange(ref _motionParseFail, 0);
        Interlocked.Exchange(ref _safetyParseSuccess, 0);
        Interlocked.Exchange(ref _safetyParseFail, 0);
        Interlocked.Exchange(ref _onvifParseSuccess, 0);
        Interlocked.Exchange(ref _onvifParseFail, 0);
        Interlocked.Exchange(ref _motionFlushSuccess, 0);
        Interlocked.Exchange(ref _motionFlushFail, 0);
        Interlocked.Exchange(ref _safetyFlushSuccess, 0);
        Interlocked.Exchange(ref _safetyFlushFail, 0);
        Interlocked.Exchange(ref _onvifFlushSuccess, 0);
        Interlocked.Exchange(ref _onvifFlushFail, 0);
        Interlocked.Exchange(ref _totalLatency, 0);
        Interlocked.Exchange(ref _latencyCount, 0);
        _avgLatency = 0;
        
        _channelStats.Clear();
        foreach (var tracker in _channelLatencyTrackers.Values)
        {
            tracker.Reset();
        }
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

/// <summary>
/// Thread-safe latency tracker for individual channels that maintains last 100 batch latencies
/// </summary>
public class ChannelLatencyTracker
{
    private readonly Queue<double> _latencies = new();
    private readonly object _lock = new();
    private const int MAX_LATENCIES = 100;

    public void AddLatency(double latencyMs)
    {
        lock (_lock)
        {
            _latencies.Enqueue(latencyMs);
            if (_latencies.Count > MAX_LATENCIES)
            {
                _latencies.Dequeue();
            }
        }
    }

    public double GetAverageLatency()
    {
        lock (_lock)
        {
            if (_latencies.Count == 0) return 0.0;
            return _latencies.Average();
        }
    }

    public void Reset()
    {
        lock (_lock)
        {
            _latencies.Clear();
        }
    }
}
