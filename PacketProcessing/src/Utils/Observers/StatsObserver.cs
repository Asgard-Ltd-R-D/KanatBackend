using System.Threading;
using PacketProcessing.Telemetry;

namespace PacketProcessing.Utils.Observers;

/// <summary>
/// Centralized statistics observer that tracks all metrics and updates the telemetry service
/// </summary>
public class StatsObserver
{
    private readonly ITelemetryService _telemetryService;
    private readonly string _serviceName;

    // Handler Service Stats
    public HandlerStats Handler { get; }
    
    // DbWriter Service Stats  
    public DbWriterStats DbWriter { get; }

    /// <summary>
    /// Update channel statistics for both raw and parsed channels
    /// </summary>
    public void UpdateChannelStats(string channelName, int capacity, int count, double utilization, int workerCount = 0)
    {
        _telemetryService.UpdateChannelStats(channelName, capacity, count, utilization, workerCount);
    }

    /// <summary>
    /// Add latency measurement for a specific channel
    /// </summary>
    public void AddChannelLatency(string channelName, double latencyMs)
    {
        _telemetryService.AddChannelLatency(channelName, latencyMs);
    }

    public StatsObserver(ITelemetryService telemetryService, string serviceName)
    {
        _telemetryService = telemetryService;
        _serviceName = serviceName;
        Handler = new HandlerStats(_telemetryService);
        DbWriter = new DbWriterStats(_telemetryService);
    }

    /// <summary>
    /// Handler service statistics
    /// </summary>
    public class HandlerStats
    {
        private readonly ITelemetryService _telemetryService;
        
        // Packet counters
        private long _packetsCaptured;
        private long _packetsParsed;
        private long _packetsDropped;
        private long _backpressureEvents;
        private long _packetsTransmitted;
        
        // Latency tracking
        private long _totalLatencyMs;
        private long _latencyCount;
        
        // Channel tracking
        private long _rawChannelCount;

        public HandlerStats(ITelemetryService telemetryService)
        {
            _telemetryService = telemetryService;
        }

        // Packet counter methods
        public void IncrementCaptured() 
        { 
            Interlocked.Increment(ref _packetsCaptured);
            _telemetryService.IncrementCaptured();
        }
        
        // Per-pipeline captured counters
        public void IncrementMotionCaptured()
            => _telemetryService.IncrementMotionCaptured();
        public void IncrementSafetyCaptured()
            => _telemetryService.IncrementSafetyCaptured();
        public void IncrementOnvifCaptured()
            => _telemetryService.IncrementOnvifCaptured();
        
        public void IncrementParsed() 
        { 
            Interlocked.Increment(ref _packetsParsed);
            _telemetryService.IncrementParsed();
        }
        
        public void IncrementDropped() 
        { 
            Interlocked.Increment(ref _packetsDropped);
            _telemetryService.IncrementDropped();
        }
        
        public void IncrementBackpressure() 
        { 
            Interlocked.Increment(ref _backpressureEvents);
            _telemetryService.IncrementBackpressure();
        }
        
        public void IncrementTransmitted() 
        { 
            Interlocked.Increment(ref _packetsTransmitted);
        }
        
        // Batch operations
        public void AddCaptured(int count) => Interlocked.Add(ref _packetsCaptured, count);
        public void AddParsed(int count) => Interlocked.Add(ref _packetsParsed, count);
        public void AddDropped(int count) => Interlocked.Add(ref _packetsDropped, count);
        public void AddBackpressure(int count) => Interlocked.Add(ref _backpressureEvents, count);
        
        // Latency tracking
        public void AddLatency(long latencyMs)
        {
            Interlocked.Add(ref _totalLatencyMs, latencyMs);
            Interlocked.Increment(ref _latencyCount);
            _telemetryService.UpdateLatency(latencyMs);
        }
        
        // Channel tracking
        public void IncrementRawChannel() => Interlocked.Increment(ref _rawChannelCount);
        public void DecrementRawChannel() => Interlocked.Decrement(ref _rawChannelCount);
        public void AddRawChannel(int count) => Interlocked.Add(ref _rawChannelCount, count);
        
        // Getters
        public long GetCaptured() => Interlocked.Read(ref _packetsCaptured);
        public long GetParsed() => Interlocked.Read(ref _packetsParsed);
        public long GetDropped() => Interlocked.Read(ref _packetsDropped);
        public long GetBackpressure() => Interlocked.Read(ref _backpressureEvents);
        public long GetTransmitted() => Interlocked.Read(ref _packetsTransmitted);
        public long GetRawChannelCount() => Interlocked.Read(ref _rawChannelCount);
        
        public double GetAverageLatency()
        {
            var totalLatency = Interlocked.Read(ref _totalLatencyMs);
            var count = Interlocked.Read(ref _latencyCount);
            return count > 0 ? (double)totalLatency / count : 0.0;
        }
        
        // Reset methods
        public void Reset()
        {
            Interlocked.Exchange(ref _packetsCaptured, 0);
            Interlocked.Exchange(ref _packetsParsed, 0);
            Interlocked.Exchange(ref _packetsDropped, 0);
            Interlocked.Exchange(ref _backpressureEvents, 0);
            Interlocked.Exchange(ref _packetsTransmitted, 0);
            Interlocked.Exchange(ref _totalLatencyMs, 0);
            Interlocked.Exchange(ref _latencyCount, 0);
            // Note: rawChannelCount is not reset as it represents actual queue state
        }
    }

    /// <summary>
    /// DbWriter service statistics
    /// </summary>
    public class DbWriterStats
    {
        private readonly ITelemetryService _telemetryService;
        
        // Counters
        private long _flushedCount;
        private long _failedCount;
        private long _parsedCount;
        private long _channelCount; // Items currently in the parsed channel
        
        // Latency tracking
        private long _totalLatencyMs;
        private long _latencyCount;

        public DbWriterStats(ITelemetryService telemetryService)
        {
            _telemetryService = telemetryService;
        }

        // Counter methods
        public void IncrementFlushed() 
        { 
            Interlocked.Increment(ref _flushedCount);
            _telemetryService.IncrementFlushed();
        }
        
        public void IncrementFailed() 
        { 
            Interlocked.Increment(ref _failedCount);
            _telemetryService.IncrementFailed();
        }
        
        public void IncrementParsed() 
        { 
            Interlocked.Increment(ref _parsedCount);
        }
        
        // Batch operations
        public void AddFlushed(int count) 
        { 
            Interlocked.Add(ref _flushedCount, count);
            _telemetryService.IncrementFlushed(count);
        }
        
        public void AddFailed(int count) 
        { 
            Interlocked.Add(ref _failedCount, count);
            _telemetryService.IncrementFailed(count);
        }
        
        public void AddParsed(int count) => Interlocked.Add(ref _parsedCount, count);
        
        // Channel tracking
        public void IncrementChannelCount() => Interlocked.Increment(ref _channelCount);
        public void DecrementChannelCount() => Interlocked.Decrement(ref _channelCount);
        public void AddChannelCount(int count) => Interlocked.Add(ref _channelCount, count);
        
        // Latency tracking
        public void AddLatency(long latencyMs)
        {
            Interlocked.Add(ref _totalLatencyMs, latencyMs);
            Interlocked.Increment(ref _latencyCount);
            _telemetryService.UpdateLatency((double)latencyMs);
        }
        
        // Getters
        public long GetFlushed() => Interlocked.Read(ref _flushedCount);
        public long GetFailed() => Interlocked.Read(ref _failedCount);
        public long GetParsed() => Interlocked.Read(ref _parsedCount);
        
        public double GetAverageLatency()
        {
            var totalLatency = Interlocked.Read(ref _totalLatencyMs);
            var count = Interlocked.Read(ref _latencyCount);
            return count > 0 ? (double)totalLatency / count : 0.0;
        }
        
        // Channel count calculation (items currently in channel)
        public int GetChannelCount()
        {
            var count = Interlocked.Read(ref _channelCount);
            return Math.Max(0, (int)count);
        }
        
        // Reset methods
        public void Reset()
        {
            Interlocked.Exchange(ref _flushedCount, 0);
            Interlocked.Exchange(ref _failedCount, 0);
            Interlocked.Exchange(ref _parsedCount, 0);
            Interlocked.Exchange(ref _channelCount, 0);
            Interlocked.Exchange(ref _totalLatencyMs, 0);
            Interlocked.Exchange(ref _latencyCount, 0);
        }
    }
}
