using Microsoft.AspNetCore.Mvc;
using PacketProcessing.Services.Networking;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Controllers;

/// <summary>
/// Controller for controlling packet capture and processing services
/// </summary>
[ApiController]
[Route("api/v1/[controller]")]
public class CaptureControlController : ControllerBase
{
    private readonly ILogger<CaptureControlController> _logger;
    private readonly CaptureService<MotionPacketEntity> _motionCaptureService;
    private readonly CaptureService<SafetyPacketEntity> _safetyCaptureService;
    private readonly CaptureService<OnVIFPacketEntity> _onvifCaptureService;

    public CaptureControlController(
        ILogger<CaptureControlController> logger,
        CaptureService<MotionPacketEntity> motionCaptureService,
        CaptureService<SafetyPacketEntity> safetyCaptureService,
        CaptureService<OnVIFPacketEntity> onvifCaptureService)
    {
        _logger = logger;
        _motionCaptureService = motionCaptureService;
        _safetyCaptureService = safetyCaptureService;
        _onvifCaptureService = onvifCaptureService;
    }

    /// <summary>
    /// Gets the status of all capture and processing services
    /// </summary>
    [HttpGet("status")]
    public ActionResult<ResponseResult<object>> GetStatus()
    {
        try
        {
            var status = new
            {
                CaptureServices = new []
                {
                    new { ServiceType = nameof(CaptureService<MotionPacketEntity>), IsCapturing = _motionCaptureService.IsCapturing },
                    new { ServiceType = nameof(CaptureService<SafetyPacketEntity>), IsCapturing = _safetyCaptureService.IsCapturing },
                    new { ServiceType = nameof(CaptureService<OnVIFPacketEntity>), IsCapturing = _onvifCaptureService.IsCapturing },
                }
            };

            var result = ResponseResult<object>.SuccessResult(status);
            return Ok(result);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get service status");
            var result = ResponseResult<object>.ServerErrorResult("Failed to get service status");
            return StatusCode(500, result);
        }
    }

    /// <summary>
    /// Starts all capture services
    /// </summary>
    [HttpPost("start")]
    public async Task<ActionResult<ResponseResult>> StartAllServices()
    {
        try
        {
            // Start capture services directly
            await _motionCaptureService.StartCaptureAsync();
            await _safetyCaptureService.StartCaptureAsync();
            await _onvifCaptureService.StartCaptureAsync();

            _logger.LogInformation("Started all capture services");
            var result = ResponseResult.SuccessResult();
            return Ok(result);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to start services");
            var result = ResponseResult.ServerErrorResult("Failed to start services");
            return StatusCode(500, result);
        }
    }

    /// <summary>
    /// Stops all capture services
    /// </summary>
    [HttpDelete("stop")]
    public async Task<ActionResult<ResponseResult>> StopAllServices()
    {
        try
        {
            // Stop capture services directly
            await _motionCaptureService.StopCaptureAsync();
            await _safetyCaptureService.StopCaptureAsync();
            await _onvifCaptureService.StopCaptureAsync();

            _logger.LogInformation("Stopped all capture services");
            var result = ResponseResult.SuccessResult();
            return Ok(result);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to stop services");
            var result = ResponseResult.ServerErrorResult("Failed to stop services");
            return StatusCode(500, result);
        }
    }
}
