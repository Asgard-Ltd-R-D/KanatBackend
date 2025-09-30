using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Services.Orchestration;
using PacketProcessing.Services.Networking;

namespace PacketProcessing.Services.Orchestration;

/// <summary>
/// Coordinates handlers and writers for all data pipes.
/// </summary>
public class PipelineOrchestrator : IPipelineOrchestrator
{
    private readonly ILogger<PipelineOrchestrator> _logger;
    private readonly IConfiguration _config;
    private readonly IDeviceService _deviceService;

    private readonly HandlerService<MotionPacketEntity> _motionHandler;
    private readonly HandlerService<SafetyPacketEntity> _safetyHandler;
    private readonly HandlerService<OnVIFPacketEntity> _onvifHandler;

    public PipelineOrchestrator(
        ILogger<PipelineOrchestrator> logger,
        IConfiguration config,
        IDeviceService deviceService,
        HandlerService<MotionPacketEntity> motionHandler,
        HandlerService<SafetyPacketEntity> safetyHandler,
        HandlerService<OnVIFPacketEntity> onvifHandler)
    {
        _logger = logger;
        _config = config;
        _deviceService = deviceService;
        _motionHandler = motionHandler;
        _safetyHandler = safetyHandler;
        _onvifHandler = onvifHandler;
    }

    public async Task StartAsync(CancellationToken cancellationToken, string deviceName)
    {
        _logger.LogInformation("Pipeline Orchestrator starting...");

        await _motionHandler.SubscribeToDeviceAsync(
            _deviceService,
            deviceName);

        await _safetyHandler.SubscribeToDeviceAsync(
            _deviceService,
            deviceName);

        await _onvifHandler.SubscribeToDeviceAsync(
            _deviceService,
            deviceName);

        _logger.LogInformation("Pipeline Orchestrator initialized all handlers.");
    }

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        _logger.LogInformation("Pipeline Orchestrator stopping...");

        await _motionHandler.UnsubscribeAsync(_deviceService);
        await _safetyHandler.UnsubscribeAsync(_deviceService);
        await _onvifHandler.UnsubscribeAsync(_deviceService);

        _logger.LogInformation("Pipeline Orchestrator stopped.");
    }

    public (long Captured, long Parsed, long Dropped) GetStats()
    {
        var motionStats = _motionHandler.GetStats();
        var safetyStats = _safetyHandler.GetStats();
        var onvifStats = _onvifHandler.GetStats();
        return (motionStats.Captured + safetyStats.Captured + onvifStats.Captured, motionStats.Parsed + safetyStats.Parsed + onvifStats.Parsed, motionStats.Dropped + safetyStats.Dropped + onvifStats.Dropped);
    }
}
