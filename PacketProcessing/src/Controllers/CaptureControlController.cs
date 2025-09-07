using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Hosting;
using PacketProcessing.Services.Networking;
using PacketProcessing.Services.Processing;
using Microsoft.Extensions.Logging;
using PacketProcessing.Entities;
using PacketProcessing.DTOs;

namespace PacketProcessing.Controllers;

/// <summary>
/// Controller for controlling packet capture and processing services
/// </summary>
[ApiController]
[Route("api/v1/[controller]")]
public class CaptureControlController : ControllerBase
{
    private readonly ILogger<CaptureControlController> _logger;
    private readonly MotionCaptureService _motionCaptureService;
    private readonly SafetyCaptureService _safetyCaptureService;
    private readonly OnVIFCaptureService _onvifCaptureService;

    public CaptureControlController(
        ILogger<CaptureControlController> logger,
        MotionCaptureService motionCaptureService,
        SafetyCaptureService safetyCaptureService,
        OnVIFCaptureService onvifCaptureService)
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
                    new { ServiceType = nameof(MotionCaptureService), IsCapturing = _motionCaptureService.IsCapturing },
                    new { ServiceType = nameof(SafetyCaptureService), IsCapturing = _safetyCaptureService.IsCapturing },
                    new { ServiceType = nameof(OnVIFCaptureService), IsCapturing = _onvifCaptureService.IsCapturing },
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
    [HttpPost("stop")]
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

    /// <summary>
    /// Gets packet statistics from all capture services
    /// </summary>
    [HttpGet("statistics")]
    public async Task<ActionResult<ResponseResult<object>>> GetStatistics()
    {
        try
        {
            var motionStats = _motionCaptureService.GetPerformanceStats();
            var safetyStats = _safetyCaptureService.GetPerformanceStats();
            var onvifStats = _onvifCaptureService.GetPerformanceStats();

            var statistics = new
            {
                CaptureServices = new
                {
                    Motion = new
                    {
                        Processed = motionStats.Processed,
                        Dropped = motionStats.Dropped,
                        Pps = motionStats.Pps,
                        IsCapturing = _motionCaptureService.IsCapturing
                    },
                    Safety = new
                    {
                        Processed = safetyStats.Processed,
                        Dropped = safetyStats.Dropped,
                        Pps = safetyStats.Pps,
                        IsCapturing = _safetyCaptureService.IsCapturing
                    },
                    OnVIF = new
                    {
                        Processed = onvifStats.Processed,
                        Dropped = onvifStats.Dropped,
                        Pps = onvifStats.Pps,
                        IsCapturing = _onvifCaptureService.IsCapturing
                    }
                },
                TotalProcessed = motionStats.Processed + safetyStats.Processed + onvifStats.Processed,
                TotalDropped = motionStats.Dropped + safetyStats.Dropped + onvifStats.Dropped,
                TotalPps = motionStats.Pps + safetyStats.Pps + onvifStats.Pps,
                Timestamp = DateTime.UtcNow
            };

            var result = ResponseResult<object>.SuccessResult(statistics);
            return Ok(result);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get packet statistics");
            var result = ResponseResult<object>.ServerErrorResult("Failed to get packet statistics");
            return StatusCode(500, result);
        }
    }

    /// <summary>
    /// Clears all packet data
    /// </summary>
    [HttpDelete("clear-all")]
    public async Task<ActionResult<ResponseResult>> ClearAllPackets()
    {
        try
        {
            _logger.LogInformation("Clear packet data requested - packet processing services are temporarily disabled");
            var result = ResponseResult.SuccessResult(200);
            return Ok(result);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to clear packet data");
            var result = ResponseResult.ServerErrorResult("Failed to clear packet data");
            return StatusCode(500, result);
        }
    }
}
