using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Services.Realtime.Networking;
using PacketProcessing.Services.Realtime.Storage;
using PacketProcessing.DTOs;
using PacketProcessing.Utils.Enums;
using PacketProcessing.Telemetry;
using PacketProcessing.DTOs.Range;
using PacketProcessing.DTOs.Conf;

namespace PacketProcessing.Services.Realtime;

/// <summary>
/// Real-time service that coordinates handlers and writers for all data pipes
/// </summary>
public class RealtimeService : IRealtimeService
{
    private readonly ILogger<RealtimeService> _logger;
    private readonly IDeviceService _deviceService;
    private readonly ITelemetryService _telemetryService;

    private readonly IHandlerService<MotionPacketEntity> _motionHandler;
    private readonly IHandlerService<SafetyPacketEntity> _safetyHandler;
    private readonly IHandlerService<OnVIFPacketEntity> _onvifHandler;

    private readonly IDbWriterService<MotionPacketEntity> _motionWriter;
    private readonly IDbWriterService<SafetyPacketEntity> _safetyWriter;
    private readonly IDbWriterService<OnVIFPacketEntity> _onvifWriter;

    private RangeDto? _currentRange;

    public bool IsActive { get; private set; }

    public RealtimeService(
        ILogger<RealtimeService> logger,
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
        _deviceService = deviceService;
        _telemetryService = telemetryService;
        _motionHandler = motionHandler;
        _safetyHandler = safetyHandler;
        _onvifHandler = onvifHandler;
        _motionWriter = motionWriter;
        _safetyWriter = safetyWriter;
        _onvifWriter = onvifWriter;
    }

    public async Task StartAsync(CancellationToken cancellationToken, BPFConfDto config)
    {
        try
        {
            _logger.LogInformation("[REALTIME-SERVICE] Starting with configuration (Device={Device})...", config.Device);

            await _motionHandler.SubscribeToDeviceAsync(_deviceService, config);
            await _safetyHandler.SubscribeToDeviceAsync(_deviceService, config);
            await _onvifHandler.SubscribeToDeviceAsync(_deviceService, config);

            IsActive = true;
            _logger.LogInformation("[REALTIME-SERVICE] Initialized all handlers with configuration");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[REALTIME-SERVICE] Start with configuration failed");
            throw;
        }
    }

    [Obsolete("Development only - use StartAsync(CancellationToken, BPFConfDto) instead")]
    public async Task StartAsync(CancellationToken cancellationToken, string deviceName)
    {
        _logger.LogInformation("[REALTIME-SERVICE] Starting...");

        await _motionHandler.SubscribeToDeviceAsync(_deviceService, deviceName);
        await _safetyHandler.SubscribeToDeviceAsync(_deviceService, deviceName);
        await _onvifHandler.SubscribeToDeviceAsync(_deviceService, deviceName);

        IsActive = true;
        _logger.LogInformation("[REALTIME-SERVICE] Initialized all handlers");
    }

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        try
        {
            _logger.LogInformation("[REALTIME-SERVICE] Stopping...");

            await _motionHandler.UnsubscribeAsync(_deviceService);
            await _safetyHandler.UnsubscribeAsync(_deviceService);
            await _onvifHandler.UnsubscribeAsync(_deviceService);

            IsActive = false;
            _logger.LogInformation("[REALTIME-SERVICE] Stopped");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[REALTIME-SERVICE] Stop failed");
            throw;
        }
    }

    
    public void ResetStats()
    {
        _logger.LogInformation("[REALTIME-SERVICE] Resetting all pipeline statistics...");
        
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
        
        _logger.LogInformation("[REALTIME-SERVICE] All pipeline statistics reset successfully");
    }

    public TelemetryDto GetStats()
    {
        // Get stats from telemetry service
        var telemetrySnapshot = _telemetryService.SnapshotAsync().GetAwaiter().GetResult();
        
        return telemetrySnapshot;
    }

    public ICollection<string> GetAvailableDeviceNames()
    {
        return _deviceService.GetAvailableDeviceNames();
    }

    public Task<RangeDto?> GetCurrentRangeAsync()
    {
        return Task.FromResult(_currentRange);
    }

    public Task SetCurrentRangeAsync(RangeDto range)
    {
        _currentRange = range;
        return Task.CompletedTask;
    }
}

