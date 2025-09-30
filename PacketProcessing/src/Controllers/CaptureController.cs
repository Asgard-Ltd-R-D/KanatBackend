using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs;
using PacketProcessing.Services.Orchestration;

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

    public CaptureController(
        ILogger<CaptureController> logger,
        IPipelineOrchestrator orchestrator)
    {
        _logger = logger;
        _orchestrator = orchestrator;
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
    /// Gets the status of all devices.
    /// </summary>
    [HttpGet("status")]
    public ActionResult<ResponseResult<object>> GetDevicesStatus()
    {
        try
        {
            var statuses = _orchestrator.GetStats();
            return Ok(ResponseResult<object>.SuccessResult(statuses));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get device statuses");
            return StatusCode(500, ResponseResult<object>.ServerErrorResult("Failed to get device statuses"));
        }
    }
}
