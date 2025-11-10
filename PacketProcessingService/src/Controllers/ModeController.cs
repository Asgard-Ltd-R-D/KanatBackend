using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs;
using PacketProcessing.Services;
using PacketProcessing.Utils.Enums;
using Microsoft.AspNetCore.Http;
using PacketProcessing.Config;
using PacketProcessing.DTOs.Range;

namespace PacketProcessing.Controllers;

/// <summary>
/// Controller for mode management, realtime control, devices and reset endpoints.
/// </summary>
[ApiController]
[Route("api/range")] // Preserve existing routes
public class ModeController : ControllerBase
{
    private readonly ILogger<ModeController> _logger;
    private readonly IRangeService _rangeService;

    public ModeController(
        ILogger<ModeController> logger,
        IRangeService rangeService)
    {
        _logger = logger;
        _rangeService = rangeService;
    }

    #region Mode Management

    [HttpPut("mode/{mode}")]
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult))]
    [ProducesResponseType(StatusCodes.Status400BadRequest, Type = typeof(ResponseResult))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult))]
    public ActionResult<ResponseResult> ChangeMode(States mode)
    {
        try
        {
            var currentMode = _rangeService.CurrentMode;
            if (currentMode == mode)
                return Ok(ResponseResult.SuccessResult());

            _rangeService.SetMode(mode);
            _logger.LogInformation("Mode changed from {CurrentMode} to {NewMode}", currentMode, mode);
            return Ok(ResponseResult.SuccessResult());
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to change mode to {Mode}", mode);
            return StatusCode(500, ResponseResult.ServerErrorResult($"Failed to change mode: {ex.Message}"));
        }
    }

    [HttpGet("mode")]
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult<string>))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult<string>))]
    public ActionResult<ResponseResult<string>> GetMode()
    {
        try
        {
            var currentMode = _rangeService.CurrentMode;
            return Ok(ResponseResult<string>.SuccessResult(currentMode.ToString()));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get current mode");
            return StatusCode(500, ResponseResult<string>.ServerErrorResult("Failed to get current mode"));
        }
    }

    #endregion

    #region Realtime

    [HttpPost("realtime/start")]
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult<RangeDto>))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult<RangeDto>))]
    public async Task<ActionResult<ResponseResult<RangeDto>>> StartRealtimeRangeAsync([FromBody]RangeDto rangeDto, CancellationToken ct)
    {
        try
        {
            var started = await _rangeService.StartRealtimeRangeAsync(ct, rangeDto);
            return Ok(ResponseResult<RangeDto>.SuccessResult(started));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to start orchestrator");
            return StatusCode(500, ResponseResult<RangeDto>.ServerErrorResult("Failed to start services"));
        }
    }

    // Development only legacy stop
    [HttpDelete("realtime/stop")]
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult<RangeDto>))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult<RangeDto>))]
    public async Task<ActionResult<ResponseResult<RangeDto>>> StopRealtimeRangeAsync(CancellationToken ct)
    {
        try
        {
            var stopped = await _rangeService.StopRealtimeRangeAsync(ct);
            _logger.LogInformation("Stopped pipeline orchestrator");
            return Ok(ResponseResult<RangeDto>.SuccessResult(stopped!));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to stop orchestrator");
            return StatusCode(500, ResponseResult<RangeDto>.ServerErrorResult("Failed to stop services"));
        }
    }

    [HttpGet("realtime/devices")]
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult<ICollection<string>>))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult<ICollection<string>>))]
    public ActionResult<ResponseResult<ICollection<string>>> GetAvailableDevices()
    {
        try
        {
            var devices = _rangeService.Realtime.GetAvailableDeviceNames();
            return Ok(ResponseResult<ICollection<string>>.SuccessResult(devices));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get available devices");
            return StatusCode(500, ResponseResult<ICollection<string>>.ServerErrorResult("Failed to get available devices"));
        }
    }

    [HttpPost("reset")]
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult))]
    public ActionResult<ResponseResult> ResetStatistics()
    {
        try
        {
            _rangeService.ResetCurrentModeStatistics();
            _logger.LogInformation("Statistics reset requested via API");
            return Ok(ResponseResult.SuccessResult());
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to reset statistics");
            return StatusCode(500, ResponseResult.ServerErrorResult("Failed to reset statistics"));
        }
    }

    #endregion

    #region Development Only

    // Development only legacy start
    [DevelopmentOnly]
    [HttpPost("dev/realtime/start/{deviceName}")]
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult))]
    public async Task<ActionResult<ResponseResult>> StartAllServices(string deviceName, CancellationToken ct)
    {
        try
        {
            await _rangeService.Realtime.StartAsync(ct, deviceName);
            _logger.LogInformation("Started pipeline orchestrator for {DeviceName}", deviceName);
            return Ok(ResponseResult.SuccessResult());
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to start orchestrator");
            return StatusCode(500, ResponseResult.ServerErrorResult("Failed to start services"));
        }
    }

    // Development only legacy stop
    [DevelopmentOnly]
    [HttpDelete("dev/realtime/stop")]
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult))]
    public async Task<ActionResult<ResponseResult>> StopAllServices(CancellationToken ct)
    {
        try
        {
            await _rangeService.Realtime.StopAsync(ct);
            _logger.LogInformation("Stopped pipeline orchestrator");
            return Ok(ResponseResult.SuccessResult());
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to stop orchestrator");
            return StatusCode(500, ResponseResult.ServerErrorResult("Failed to stop services"));
        }
    }

    #endregion

    #region Playback

    [HttpPut("playback/pace/{pace}")]
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult))]
    [ProducesResponseType(StatusCodes.Status400BadRequest, Type = typeof(ResponseResult))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult))]
    public ActionResult<ResponseResult> SetPlaybackPace(double pace)
    {
        try
        {
            if (pace <= 0)
                return BadRequest(ResponseResult.ErrorResult("Pace must be greater than 0"));

            _logger.LogInformation("Playback pace set to {Pace}", pace);
            return Ok(ResponseResult.SuccessResult());
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to set playback pace");
            return StatusCode(500, ResponseResult.ServerErrorResult("Failed to set playback pace"));
        }
    }

    #endregion
}


