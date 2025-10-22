using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Services.Realtime.Networking;
using PacketProcessing.Services.Realtime.Storage;
using PacketProcessing.DTOs;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Services.Realtime;

/// <summary>
/// Real-time service that coordinates handlers and writers for all data pipes
/// </summary>
public class RealtimeService : IRealtimeService
{
    private readonly ILogger<RealtimeService> _logger;
    private readonly IConfiguration _config;
    private readonly IDeviceService _deviceService;

    private readonly IHandlerService<MotionPacketEntity> _motionHandler;
    private readonly IHandlerService<SafetyPacketEntity> _safetyHandler;
    private readonly IHandlerService<OnVIFPacketEntity> _onvifHandler;

    private readonly IDbWriterService<MotionPacketEntity> _motionWriter;
    private readonly IDbWriterService<SafetyPacketEntity> _safetyWriter;
    private readonly IDbWriterService<OnVIFPacketEntity> _onvifWriter;

    public RealtimeService(
        ILogger<RealtimeService> logger,
        IConfiguration config,
        IDeviceService deviceService,
        IHandlerService<MotionPacketEntity> motionHandler,
        IHandlerService<SafetyPacketEntity> safetyHandler,
        IHandlerService<OnVIFPacketEntity> onvifHandler,
        IDbWriterService<MotionPacketEntity> motionWriter,
        IDbWriterService<SafetyPacketEntity> safetyWriter,
        IDbWriterService<OnVIFPacketEntity> onvifWriter)
    {
        _logger = logger;
        _config = config;
        _deviceService = deviceService;
        _motionHandler = motionHandler;
        _safetyHandler = safetyHandler;
        _onvifHandler = onvifHandler;
        _motionWriter = motionWriter;
        _safetyWriter = safetyWriter;
        _onvifWriter = onvifWriter;
    }

    public async Task StartAsync(CancellationToken cancellationToken, string deviceName)
    {
        _logger.LogInformation("Realtime service starting...");

        await _motionHandler.SubscribeToDeviceAsync(_deviceService, deviceName);
        await _safetyHandler.SubscribeToDeviceAsync(_deviceService, deviceName);
        await _onvifHandler.SubscribeToDeviceAsync(_deviceService, deviceName);

        _logger.LogInformation("Realtime service initialized all handlers");
    }

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        _logger.LogInformation("Realtime service stopping...");

        await _motionHandler.UnsubscribeAsync(_deviceService);
        await _safetyHandler.UnsubscribeAsync(_deviceService);
        await _onvifHandler.UnsubscribeAsync(_deviceService);

        _logger.LogInformation("Realtime service stopped");
    }

    public TelemetryDto GetStats()
    {
        // Get handler stats
        var motionStats = _motionHandler.GetStats();
        var safetyStats = _safetyHandler.GetStats();
        var onvifStats = _onvifHandler.GetStats();
        
        // Get backpressure events
        var motionBackpressure = _motionHandler.GetBackpressureEvents();
        var safetyBackpressure = _safetyHandler.GetBackpressureEvents();
        var onvifBackpressure = _onvifHandler.GetBackpressureEvents();
        
        // Get writer stats
        var motionWriterStats = _motionWriter.GetStats();
        var safetyWriterStats = _safetyWriter.GetStats();
        var onvifWriterStats = _onvifWriter.GetStats();
        
        if (motionBackpressure > 0 || safetyBackpressure > 0 || onvifBackpressure > 0)
        {
            _logger.LogWarning("Backpressure detected - Motion: {Motion}, Safety: {Safety}, OnVIF: {OnVIF}", 
                motionBackpressure, safetyBackpressure, onvifBackpressure);
        }

        // Calculate average latency across handlers and writers
        var handlerAvgLatency = (motionStats.AvgLatencyMs + safetyStats.AvgLatencyMs + onvifStats.AvgLatencyMs) / 3.0;
        var writerAvgLatency = (motionWriterStats.AvgLatencyMs + safetyWriterStats.AvgLatencyMs + onvifWriterStats.AvgLatencyMs) / 3.0;
        var totalAvgLatency = handlerAvgLatency + writerAvgLatency;

        // Get channel counts for both raw (capture->parse) and parsed (parse->db) channels
        var motionRawCount = _motionHandler.GetRawChannelCount();
        var safetyRawCount = _safetyHandler.GetRawChannelCount();
        var onvifRawCount = _onvifHandler.GetRawChannelCount();
        
        // Calculate parsed channel counts as (parsed - flushed) = items waiting to be written
        var motionParsedCount = Math.Max(0, (int)(motionStats.Parsed - motionWriterStats.Flushed));
        var safetyParsedCount = Math.Max(0, (int)(safetyStats.Parsed - safetyWriterStats.Flushed));
        var onvifParsedCount = Math.Max(0, (int)(onvifStats.Parsed - onvifWriterStats.Flushed));

        return new TelemetryDto
        {
            Captured = motionStats.Captured + safetyStats.Captured + onvifStats.Captured,
            Parsed = motionStats.Parsed + safetyStats.Parsed + onvifStats.Parsed,
            Dropped = motionStats.Dropped + safetyStats.Dropped + onvifStats.Dropped,
            Flushed = motionWriterStats.Flushed + safetyWriterStats.Flushed + onvifWriterStats.Flushed,
            Failed = motionWriterStats.Failed + safetyWriterStats.Failed + onvifWriterStats.Failed,
            Backpressure = motionBackpressure + safetyBackpressure + onvifBackpressure,
            AvgLatency = totalAvgLatency,
            MotionCaptured = motionStats.Captured,
            SafetyCaptured = safetyStats.Captured,
            OnvifCaptured = onvifStats.Captured,
            // Raw channels (Capture -> Parse)
            MotionRawChannel = new ChannelStatsDto
            {
                Capacity = 500_000,
                CurrentSize = motionRawCount >= 0 ? motionRawCount : 0,
                UtilizationPercent = motionRawCount >= 0 ? (motionRawCount / 500_000.0) * 100 : 0
            },
            SafetyRawChannel = new ChannelStatsDto
            {
                Capacity = 500_000,
                CurrentSize = safetyRawCount >= 0 ? safetyRawCount : 0,
                UtilizationPercent = safetyRawCount >= 0 ? (safetyRawCount / 500_000.0) * 100 : 0
            },
            OnvifRawChannel = new ChannelStatsDto
            {
                Capacity = 500_000,
                CurrentSize = onvifRawCount >= 0 ? onvifRawCount : 0,
                UtilizationPercent = onvifRawCount >= 0 ? (onvifRawCount / 500_000.0) * 100 : 0
            },
            // Parsed channels (Parse -> DB)
            MotionParsedChannel = new ChannelStatsDto
            {
                Capacity = 1_000_000,
                CurrentSize = motionParsedCount >= 0 ? motionParsedCount : 0,
                UtilizationPercent = motionParsedCount >= 0 ? (motionParsedCount / 1_000_000.0) * 100 : 0
            },
            SafetyParsedChannel = new ChannelStatsDto
            {
                Capacity = 1_000_000,
                CurrentSize = safetyParsedCount >= 0 ? safetyParsedCount : 0,
                UtilizationPercent = safetyParsedCount >= 0 ? (safetyParsedCount / 1_000_000.0) * 100 : 0
            },
            OnvifParsedChannel = new ChannelStatsDto
            {
                Capacity = 100_000,
                CurrentSize = onvifParsedCount >= 0 ? onvifParsedCount : 0,
                UtilizationPercent = onvifParsedCount >= 0 ? (onvifParsedCount / 100_000.0) * 100 : 0
            }
        };
    }
    
    public void ResetStats()
    {
        _logger.LogInformation("Resetting all pipeline statistics...");
        
        // Reset handler stats
        _motionHandler.ResetStats();
        _safetyHandler.ResetStats();
        _onvifHandler.ResetStats();
        
        // Reset writer stats
        _motionWriter.ResetStats();
        _safetyWriter.ResetStats();
        _onvifWriter.ResetStats();
        
        _logger.LogInformation("All pipeline statistics reset successfully");
    }
}

