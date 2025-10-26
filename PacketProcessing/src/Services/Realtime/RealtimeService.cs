using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Services.Realtime.Networking;
using PacketProcessing.Services.Realtime.Storage;
using PacketProcessing.DTOs;
using PacketProcessing.Utils.Enums;
using PacketProcessing.Telemetry;

namespace PacketProcessing.Services.Realtime;

/// <summary>
/// Real-time service that coordinates handlers and writers for all data pipes
/// </summary>
public class RealtimeService : IRealtimeService
{
    private readonly ILogger<RealtimeService> _logger;
    private readonly IConfiguration _config;
    private readonly IDeviceService _deviceService;
    private readonly ITelemetryService _telemetryService;

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
        ITelemetryService telemetryService,
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
        _telemetryService = telemetryService;
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
        
        // Reset telemetry service
        _telemetryService.Reset();
        
        _logger.LogInformation("All pipeline statistics reset successfully");
    }

    public TelemetryDto GetStats()
    {
        // Get stats from telemetry service
        var telemetrySnapshot = _telemetryService.SnapshotAsync().GetAwaiter().GetResult();
        
        return telemetrySnapshot;
    }
}

