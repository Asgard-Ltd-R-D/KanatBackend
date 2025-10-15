using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using PacketProcessing.DTOs;
using PacketProcessing.Services.Orchestration;

namespace PacketProcessing.Controllers;

/// <summary>
/// Controller for playback of recorded packet data.
/// </summary>
[ApiController]
[Route("api/v1/[controller]")]
public class PlaybackController : ControllerBase
{
    private readonly ILogger<PlaybackController> _logger;
    private readonly IConfiguration _configuration;
    private readonly IPipelineOrchestrator _orchestrator;

    public PlaybackController(
        ILogger<PlaybackController> logger,
        IConfiguration configuration,
        IPipelineOrchestrator orchestrator)
    {
        _logger = logger;
        _configuration = configuration;
        _orchestrator = orchestrator;
    }

    /// <summary>
    /// Placeholder for future playback functionality.
    /// </summary>
    [HttpGet("status")]
    public ActionResult<ResponseResult<object>> GetPlaybackStatus()
    {
        try
        {
            var status = new
            {
                Message = "Playback functionality coming soon",
                CurrentState = _orchestrator.GetCurrentState().ToString()
            };
            
            return Ok(ResponseResult<object>.SuccessResult(status));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get playback status");
            return StatusCode(500, ResponseResult<object>.ServerErrorResult("Failed to get playback status"));
        }
    }
}

