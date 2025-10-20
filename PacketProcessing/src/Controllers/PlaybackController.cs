using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using PacketProcessing.DTOs;
using PacketProcessing.Services;

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
    private readonly IStateManager _stateManager;

    public PlaybackController(
        ILogger<PlaybackController> logger,
        IConfiguration configuration,
        IStateManager stateManager)
    {
        _logger = logger;
        _configuration = configuration;
        _stateManager = stateManager;
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
                CurrentState = _stateManager.CurrentState.ToString()
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

