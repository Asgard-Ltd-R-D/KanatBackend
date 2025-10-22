using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using PacketProcessing.Config;
using PacketProcessing.DTOs;
using PacketProcessing.DTOs.Range;
using PacketProcessing.Services;
using PacketProcessing.Services.Realtime.Networking;
using PacketProcessing.Utils.Enums;

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
    /// <param name="mode">The target mode (realtime or playback)</param>
    [HttpPut("mode/{mode}")]
    public ActionResult<ResponseResult> ChangeMode(string mode)
    {
        try
        {
            // Parse the mode
            if (!Enum.TryParse<States>(mode, true, out var targetMode))
            {
                var errorMessage = $"Invalid mode: {mode}. Valid modes are: Realtime, Playback";
                return BadRequest(ResponseResult.ErrorResult(errorMessage));
            }

            var currentMode = _rangeService.CurrentMode;
            
            // Check if already in the target mode
            if (currentMode == targetMode)
            {
                return Ok(ResponseResult.SuccessResult());
            }

            // Validate the mode transition
            var validationResult = ValidateModeTransition(currentMode, targetMode);
            if (!validationResult.IsValid)
            {
                return BadRequest(ResponseResult.ErrorResult(validationResult.ErrorMessage));
            }

            // Change the mode
            _rangeService.SetMode(targetMode);
            _logger.LogInformation("Mode changed from {CurrentMode} to {NewMode}", currentMode, targetMode);
            
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
    /// Gets the telemetry status of all devices.
    /// </summary>
    [HttpGet("realtime/status")]
    public ActionResult<ResponseResult<TelemetryDto>> GetDevicesStatus()
    {
        try
        {
            var telemetry = _rangeService.Realtime.GetStats();
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
    /// Resets all statistics counters to zero.
    /// </summary>
    [HttpPost("realtime/reset")]
    public ActionResult<ResponseResult> ResetStatistics()
    {
        try
        {
            _rangeService.Realtime.ResetStats();
            _logger.LogInformation("Statistics reset requested via API");
            return Ok(ResponseResult.SuccessResult());
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to reset statistics");
            return StatusCode(500, ResponseResult.ServerErrorResult("Failed to reset statistics"));
        }
    }

    /// <summary>
    /// Gets the current configuration settings.
    /// </summary>
    [HttpGet("realtime/config")]
    public ActionResult<ResponseResult<object>> GetConfiguration()
    {
        try
        {
            var config = new
            {
                Environment = _configuration["ASPNETCORE_ENVIRONMENT"] ?? "Unknown",
                Concurrency = new
                {
                    MinWorkers = _configuration.GetValue<int>("Concurrency:MinWorkers"),
                    MaxWorkers = _configuration.GetValue<int>("Concurrency:MaxWorkers"),
                    BatchSize = _configuration.GetValue<int>("Concurrency:BatchSize"),
                    BatchTimeoutMs = _configuration.GetValue<int>("Concurrency:BatchTimeoutMs")
                },
                DataPipes = new
                {
                    MotionCapture = new
                    {
                        Channel = new
                        {
                            Members = _configuration.GetValue<int>("DataPipes:MotionCapture:Channel:Members")
                        },
                        Network = new
                        {
                            Protocol = _configuration.GetValue<string>("DataPipes:MotionCapture:Network:Protocol"),
                            IPs = _configuration.GetSection("DataPipes:MotionCapture:Network:IPs").Get<string[]>()
                        }
                    },
                    SafetyCapture = new
                    {
                        Channel = new
                        {
                            Members = _configuration.GetValue<int>("DataPipes:SafetyCapture:Channel:Members")
                        },
                        Network = new
                        {
                            Protocol = _configuration.GetValue<string>("DataPipes:SafetyCapture:Network:Protocol"),
                            IPs = _configuration.GetSection("DataPipes:SafetyCapture:Network:IPs").Get<string[]>()
                        }
                    },
                    OnVIFCapture = new
                    {
                        Channel = new
                        {
                            Members = _configuration.GetValue<int>("DataPipes:OnVIFCapture:Channel:Members")
                        },
                        Network = new
                        {
                            Protocol = _configuration.GetValue<string>("DataPipes:OnVIFCapture:Network:Protocol"),
                            IPs = _configuration.GetSection("DataPipes:OnVIFCapture:Network:IPs").Get<string[]>()
                        }
                    }
                },
                HubTransmission = new
                {
                    IntervalMs = _configuration.GetValue<int>("HubTransmission:IntervalMs", 30)
                }
            };
            
            return Ok(ResponseResult<object>.SuccessResult(config));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get configuration");
            return StatusCode(500, ResponseResult<object>.ServerErrorResult("Failed to get configuration"));
        }
    }

    #endregion

    #region Playback

    /// <summary>
    /// Gets the playback status.
    /// </summary>
    [HttpGet("playback/status")]
    public ActionResult<ResponseResult<object>> GetPlaybackStatus()
    {
        try
        {
            var status = new
            {
                Message = "Playback functionality coming soon",
                CurrentMode = _rangeService.CurrentMode.ToString()
            };
            
            return Ok(ResponseResult<object>.SuccessResult(status));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get playback status");
            return StatusCode(500, ResponseResult<object>.ServerErrorResult("Failed to get playback status"));
        }
    }

    /// <summary>
    /// Sets the playback pace (speed multiplier).
    /// </summary>
    /// <param name="pace">The playback pace multiplier (e.g., 1.0 = normal speed, 2.0 = double speed)</param>
    [HttpPut("playback/pace")]
    public ActionResult<ResponseResult> SetPlaybackPace([FromBody] double pace)
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
    /// Gets all ranges with pagination.
    /// </summary>
    /// <param name="page">Page number (1-based)</param>
    /// <param name="pageSize">Number of items per page</param>
    [HttpGet("ranges")]
    public async Task<ActionResult<ResponseResult<PaginatedResult<RangeDto>>>> GetAllRangesPaginated(
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
    [HttpGet("ranges/all")]
    [DevelopmentOnly]
    public async Task<ActionResult<ResponseResult<IEnumerable<RangeDto>>>> GetAllRanges()
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
    [HttpDelete("ranges/all")]
    [DevelopmentOnly]
    public async Task<ActionResult<ResponseResult<int>>> DeleteAll()
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
    /// <param name="start">Start timestamp</param>
    /// <param name="end">End timestamp</param>
    [HttpDelete("packets/clear")]
    public async Task<ActionResult<ResponseResult<string>>> ClearPacketsAsync([FromQuery] long start, [FromQuery] long end)
    {
        try
        {
            var result = await _rangeService.ClearPacketsAsync(start, end);
            if (!result)
            {
                return BadRequest(ResponseResult<string>.ErrorResult("Failed to clear packets"));
            }
            
            return Ok(ResponseResult<string>.SuccessResult("Packet clearing will be implemented in repository"));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to clear packets");
            return StatusCode(500, ResponseResult<string>.ServerErrorResult("Failed to clear packets"));
        }
    }

    #endregion
}

