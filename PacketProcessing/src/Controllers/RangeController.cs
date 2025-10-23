using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using PacketProcessing.Config;
using PacketProcessing.DTOs;
using PacketProcessing.DTOs.Range;
using PacketProcessing.Services;
using PacketProcessing.Services.Realtime.Networking;
using PacketProcessing.Utils.Enums;
using Microsoft.AspNetCore.Http;

namespace PacketProcessing.Controllers;

/// <summary>
/// Controller for managing range operations including mode control, capture, playback, and range entity management.
/// </summary>
[ApiController]
[Route("api/v1/[controller]")]
public class RangeController : ControllerBase
{
    private readonly ILogger<RangeController> _logger;
    private readonly IConfiguration _configuration;
    private readonly IRangeService _rangeService;
    private readonly IDeviceService _deviceService;

    public RangeController(
        ILogger<RangeController> logger,
        IConfiguration configuration,
        IRangeService rangeService,
        IDeviceService deviceService)
    {
        _logger = logger;
        _configuration = configuration;
        _rangeService = rangeService;
        _deviceService = deviceService;
    }

    #region Mode Management

    /// <summary>
    /// Changes the application mode between Realtime and Playback.
    /// </summary>
    /// <param name="mode">The target mode</param>
    [HttpPut("mode/{mode}")]
    public ActionResult<ResponseResult> ChangeMode(States mode)
    {
        try
        {
            var currentMode = _rangeService.CurrentMode;
            
            // Check if already in the target mode
            if (currentMode == mode)
            {
                return Ok(ResponseResult.SuccessResult());
            }

            // Validate the mode transition
            var validationResult = ValidateModeTransition(currentMode, mode);
            if (!validationResult.IsValid)
            {
                return BadRequest(ResponseResult.ErrorResult(validationResult.ErrorMessage));
            }

            // Change the mode
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

    /// <summary>
    /// Gets the current application mode.
    /// </summary>
    [HttpGet("mode")]
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

    private (bool IsValid, string ErrorMessage) ValidateModeTransition(States currentMode, States targetMode)
    {
        // Validate Realtime to Playback transition
        if (currentMode == States.Realtime && targetMode == States.Playback)
        {
            var telemetry = _rangeService.Realtime.GetStats();
            if (telemetry.Captured > 0 && telemetry.Captured > telemetry.Flushed)
            {
                return (false, "Cannot switch to Playback mode while capture may be active. Please ensure capture is stopped.");
            }
        }
        
        // TODO: Add validation for Playback to Realtime when playback is implemented
        
        return (true, string.Empty);
    }

    #endregion

    #region Realtime

    /// <summary>
    /// Starts all realtime capture services.
    /// </summary>
    [HttpPost("realtime/start/{deviceName}")]
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

    /// <summary>
    /// Stops all realtime capture services.
    /// </summary>
    [HttpDelete("realtime/stop")]
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

    /// <summary>
    /// Gets the list of available network devices.
    /// </summary>
    [HttpGet("realtime/devices")]
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
    /// Gets the status of the current mode.
    /// </summary>
    [HttpGet("status")]
    public ActionResult<ResponseResult<object>> GetStatus()
    {
        try
        {
            var status = _rangeService.GetCurrentModeStatus();
            return Ok(ResponseResult<object>.SuccessResult(status));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get status");
            return StatusCode(500, ResponseResult<object>.ServerErrorResult("Failed to get status"));
        }
    }

    /// <summary>
    /// Resets statistics for the current mode.
    /// </summary>
    [HttpPost("reset")]
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

    #region Playback


    /// <summary>
    /// Sets the playback pace (speed multiplier).
    /// </summary>
    /// <param name="pace">The playback pace multiplier (e.g., 1.0 = normal speed, 2.0 = double speed)</param>
    [HttpPut("playback/pace/{pace}")]
    public ActionResult<ResponseResult> SetPlaybackPace(double pace)
    {
        try
        {
            if (pace <= 0)
            {
                return BadRequest(ResponseResult.ErrorResult("Pace must be greater than 0"));
            }

            // TODO: Implement playback pace in PlaybackService
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

    #region Range Entity Management

    /// <summary>
    /// Gets a range by ID.
    /// </summary>
    /// <param name="id">The range ID</param>
    [HttpGet("ranges/{id}")]
    public async Task<ActionResult<ResponseResult<RangeDto>>> GetRangeByIdAsync(Guid id)
    {
        try
        {
            var dto = await _rangeService.GetRangeByIdAsync(id);
            if (dto == null)
            {
                return NotFound(ResponseResult<RangeDto>.ErrorResult("Range not found"));
            }

            return Ok(ResponseResult<RangeDto>.SuccessResult(dto));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get range by ID {Id}", id);
            return StatusCode(500, ResponseResult<RangeDto>.ServerErrorResult("Failed to get range"));
        }
    }

    /// <summary>
    /// Creates a new range.
    /// </summary>
    /// <param name="dto">The range data to create</param>
    [HttpPost("ranges")]
    public async Task<ActionResult<ResponseResult<RangeDto>>> CreateRangeAsync([FromBody] RangeDto dto)
    {
        try
        {
            var createdDto = await _rangeService.CreateRangeAsync(dto);
            return Ok(ResponseResult<RangeDto>.SuccessResult(createdDto));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to create range");
            return StatusCode(500, ResponseResult<RangeDto>.ServerErrorResult("Failed to create range"));
        }
    }

    /// <summary>
    /// Gets all ranges with pagination.
    /// </summary>
    /// <param name="page">Page number (1-based)</param>
    /// <param name="pageSize">Number of items per page</param>
    [HttpGet("ranges")]
    public async Task<ActionResult<ResponseResult<PaginatedResult<RangeDto>>>> GetAllRangesPaginatedAsync(
        [FromQuery] int page = 1, 
        [FromQuery] int pageSize = 1000)
    {
        try
        {
            var paginatedResult = await _rangeService.GetAllRangesPaginatedAsync(page, pageSize);
            return Ok(ResponseResult<PaginatedResult<RangeDto>>.SuccessResult(paginatedResult));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get paginated ranges");
            return StatusCode(500, ResponseResult<PaginatedResult<RangeDto>>.ServerErrorResult("Failed to get ranges"));
        }
    }

    /// <summary>
    /// Gets all ranges (Development only).
    /// </summary>
    [HttpGet("dev/ranges/all")]
    [DevelopmentOnly]
    public async Task<ActionResult<ResponseResult<IEnumerable<RangeDto>>>> GetAllRangesAsync()
    {
        try
        {
            var dtos = await _rangeService.GetAllRangesAsync();
            return Ok(ResponseResult<IEnumerable<RangeDto>>.SuccessResult(dtos));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get all ranges");
            return StatusCode(500, ResponseResult<IEnumerable<RangeDto>>.ServerErrorResult("Failed to get all ranges"));
        }
    }

    /// <summary>
    /// Updates a range by ID.
    /// </summary>
    /// <param name="id">The range ID</param>
    /// <param name="dto">The updated range data</param>
    [HttpPut("ranges/{id}")]
    public async Task<ActionResult<ResponseResult<RangeDto>>> UpdateRangeByIdAsync(Guid id, [FromBody] RangeDto dto)
    {
        try
        {
            var updatedDto = await _rangeService.UpdateRangeByIdAsync(id, dto);
            if (updatedDto == null)
            {
                return NotFound(ResponseResult<RangeDto>.ErrorResult("Range not found"));
            }

            return Ok(ResponseResult<RangeDto>.SuccessResult(updatedDto));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to update range {Id}", id);
            return StatusCode(500, ResponseResult<RangeDto>.ServerErrorResult("Failed to update range"));
        }
    }

    /// <summary>
    /// Deletes a range by ID.
    /// </summary>
    /// <param name="id">The range ID</param>
    [HttpDelete("ranges/{id}")]
    public async Task<ActionResult<ResponseResult>> DeleteRangeByIdAsync(Guid id)
    {
        try
        {
            var deleted = await _rangeService.DeleteRangeByIdAsync(id);
            if (!deleted)
            {
                return NotFound(ResponseResult.ErrorResult("Range not found"));
            }

            return Ok(ResponseResult.SuccessResult());
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to delete range {Id}", id);
            return StatusCode(500, ResponseResult.ServerErrorResult("Failed to delete range"));
        }
    }

    /// <summary>
    /// Deletes all ranges (Development only).
    /// </summary>
    [HttpDelete("dev/ranges/all")]
    [DevelopmentOnly]
    public async Task<ActionResult<ResponseResult<int>>> DeleteAllAsync()
    {
        try
        {
            var count = await _rangeService.DeleteAllRangesAsync();
            return Ok(ResponseResult<int>.SuccessResult(count));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to delete all ranges");
            return StatusCode(500, ResponseResult<int>.ServerErrorResult("Failed to delete all ranges"));
        }
    }

    /// <summary>
    /// Clears packets within a time range (to be implemented in repository).
    /// </summary>
    /// <param name="start">Start timestamp (ISO-8601, assumed UTC if with 'Z')</param>
    /// <param name="end">End timestamp (ISO-8601, assumed UTC if with 'Z')</param>
    [HttpDelete("packets/clear")]
    public async Task<ActionResult<ResponseResult<string>>> ClearPacketsAsync([FromQuery] DateTime start, [FromQuery] DateTime end)
    {
        try
        {
            var result = await _rangeService.ClearPacketsAsync(start, end);
            if (!result)
            {
                return BadRequest(ResponseResult<string>.ErrorResult("Failed to clear packets"));
            }
            
            return Ok(ResponseResult<string>.SuccessResult("Packets cleared for the requested time range"));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to clear packets");
            return StatusCode(500, ResponseResult<string>.ServerErrorResult("Failed to clear packets"));
        }
    }

    #endregion
}

