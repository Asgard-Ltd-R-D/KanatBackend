using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using PacketProcessing.DTOs;
using PacketProcessing.Services;
using PacketProcessing.Services.Realtime.Networking;

namespace PacketProcessing.Controllers;

/// <summary>
/// Controller for controlling real-time packet capture and processing services.
/// </summary>
[ApiController]
[Route("api/v1/[controller]")]
public class CaptureController : ControllerBase
{
    private readonly ILogger<CaptureController> _logger;
    private readonly IConfiguration _configuration;
    private readonly IStateManager _stateManager;
    private readonly IDeviceService _deviceService;

    public CaptureController(
        ILogger<CaptureController> logger,
        IConfiguration configuration,
        IStateManager stateManager,
        IDeviceService deviceService)
    {
        _logger = logger;
        _configuration = configuration;
        _stateManager = stateManager;
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
            await _stateManager.Realtime.StartAsync(ct, deviceName);
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
            await _stateManager.Realtime.StopAsync(ct);
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
            var telemetry = _stateManager.Realtime.GetStats();
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
            _stateManager.Realtime.ResetStats();
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
    [HttpGet("config")]
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
}
