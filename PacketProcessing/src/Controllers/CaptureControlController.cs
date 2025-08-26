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
    private readonly IEnumerable<IHostedService> _captureServices;
    private readonly MotionPacketService _motionPacketService;
    private readonly SafetyPacketService _safetyPacketService;
    private readonly OnVIFPacketService _onvifPacketService;

    public CaptureControlController(
        ILogger<CaptureControlController> logger,
        IEnumerable<IHostedService> captureServices,
        MotionPacketService motionPacketService,
        SafetyPacketService safetyPacketService,
        OnVIFPacketService onvifPacketService)
    {
        _logger = logger;
        _captureServices = captureServices.Where(s => s is BaseCaptureService<BasePacketEntity>);
        _motionPacketService = motionPacketService;
        _safetyPacketService = safetyPacketService;
        _onvifPacketService = onvifPacketService;
    }

    /// <summary>
    /// Gets the status of all capture and processing services
    /// </summary>
    [HttpGet("status")]
    public ActionResult<ResponseResult<object>> GetStatus()
    {
        try
        {
            var captureServices = _captureServices.OfType<BaseCaptureService<BasePacketEntity>>().ToList();
            
            var status = new
            {
                CaptureServices = captureServices.Select(s => new
                {
                    ServiceType = s.GetType().Name,
                    IsCapturing = s.IsCapturing
                }),
                PacketProcessingServices = new[]
                {
                    new { ServiceType = "MotionPacketService", IsRunning = true },
                    new { ServiceType = "SafetyPacketService", IsRunning = true },
                    new { ServiceType = "OnVIFPacketService", IsRunning = true }
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
    /// Starts all capture and processing services
    /// </summary>
    [HttpPost("start")]
    public async Task<ActionResult<ResponseResult>> StartAllServices()
    {
        try
        {
            var captureServices = _captureServices.OfType<BaseCaptureService<BasePacketEntity>>().ToList();
            
            // Start capture services first
            foreach (var captureService in captureServices)
            {
                await captureService.StartCaptureAsync();
            }

            // Start processing services
            await _motionPacketService.StartAsync();
            await _safetyPacketService.StartAsync();
            await _onvifPacketService.StartAsync();

            _logger.LogInformation("Started all capture and processing services");
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
    /// Stops all capture and processing services
    /// </summary>
    [HttpPost("stop")]
    public async Task<ActionResult<ResponseResult>> StopAllServices()
    {
        try
        {
            var captureServices = _captureServices.OfType<BaseCaptureService<BasePacketEntity>>().ToList();
            
            // Stop processing services first
            await _motionPacketService.StopAsync();
            await _safetyPacketService.StopAsync();
            await _onvifPacketService.StopAsync();

            // Stop capture services
            foreach (var captureService in captureServices)
            {
                await captureService.StopCaptureAsync();
            }

            _logger.LogInformation("Stopped all capture and processing services");
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
    /// Gets packet statistics from all processing services
    /// </summary>
    [HttpGet("statistics")]
    public async Task<ActionResult<ResponseResult<object>>> GetStatistics()
    {
        try
        {
            var motionPackets = await _motionPacketService.GetAllAsync();
            var safetyPackets = await _safetyPacketService.GetAllAsync();
            var onvifPackets = await _onvifPacketService.GetAllAsync();

            var statistics = new
            {
                MotionPackets = motionPackets.Count(),
                SafetyPackets = safetyPackets.Count(),
                OnVIFPackets = onvifPackets.Count(),
                TotalPackets = motionPackets.Count() + safetyPackets.Count() + onvifPackets.Count()
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
            await _motionPacketService.DeleteAllAsync();
            await _safetyPacketService.DeleteAllAsync();
            await _onvifPacketService.DeleteAllAsync();

            _logger.LogInformation("Cleared all packet data");
            var result = ResponseResult.SuccessResult();
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
