using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs;
using PacketProcessing.Services.Orchestration;
using PacketProcessing.Services.Networking;

namespace PacketProcessing.Controllers;

/// <summary>
/// Controller for controlling packet capture and processing services.
/// </summary>
[ApiController]
[Route("api/v1/[controller]")]
public class CaptureController : ControllerBase
{
    private readonly ILogger<CaptureController> _logger;
    private readonly IPipelineOrchestrator _orchestrator;
    private readonly IDeviceService _deviceService;

    public CaptureController(
        ILogger<CaptureController> logger,
        IPipelineOrchestrator orchestrator,
        IDeviceService deviceService)
    {
        _logger = logger;
        _orchestrator = orchestrator;
        _deviceService = deviceService;
    }

    /// <summary>
    /// Starts all capture services.
    /// </summary>
    [HttpPost("start/{deviceName}")]
    public async Task<ActionResult<ResponseResult>> StartAllServices(string deviceName, CancellationToken ct)
    {
        try
        {
            await _orchestrator.StartAsync(ct, deviceName);
            _logger.LogInformation("Started pipeline orchestrator for {DeviceName}", deviceName);

            return Ok(ResponseResult.SuccessResult());
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to start orchestrator");
            return StatusCode(500, ResponseResult.ServerErrorResult("Failed to start services"));
        }
    }

    /// <summary>
    /// Stops all capture services.
    /// </summary>
    [HttpDelete("stop")]
    public async Task<ActionResult<ResponseResult>> StopAllServices(CancellationToken ct)
    {
        try
        {
            await _orchestrator.StopAsync(ct);
            _logger.LogInformation("Stopped pipeline orchestrator");

            return Ok(ResponseResult.SuccessResult());
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to stop orchestrator");
            return StatusCode(500, ResponseResult.ServerErrorResult("Failed to stop services"));
        }
    }

    /// <summary>
    /// Gets the telemetry status of all devices.
    /// </summary>
    [HttpGet("status")]
    public ActionResult<ResponseResult<TelemetryDto>> GetDevicesStatus()
    {
        try
        {
            var telemetry = _orchestrator.GetStats();
            return Ok(ResponseResult<TelemetryDto>.SuccessResult(telemetry));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get telemetry status");
            return StatusCode(500, ResponseResult<TelemetryDto>.ServerErrorResult("Failed to get telemetry status"));
        }
    }

    /// <summary>
    /// Gets the list of available network devices.
    /// </summary>
    [HttpGet("devices")]
    public ActionResult<ResponseResult<ICollection<string>>> GetAvailableDevices()
    {
        try
        {
            var devices = _deviceService.GetAvailableDeviceNames();
            return Ok(ResponseResult<ICollection<string>>.SuccessResult(devices));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get available devices");
            return StatusCode(500, ResponseResult<ICollection<string>>.ServerErrorResult("Failed to get available devices"));
        }
    }

    /// <summary>
    /// Resets all statistics counters to zero.
    /// </summary>
    [HttpPost("reset")]
    public ActionResult<ResponseResult> ResetStatistics()
    {
        try
        {
            _orchestrator.ResetStats();
            _logger.LogInformation("Statistics reset requested via API");
            return Ok(ResponseResult.SuccessResult());
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to reset statistics");
            return StatusCode(500, ResponseResult.ServerErrorResult("Failed to reset statistics"));
        }
    }
}
