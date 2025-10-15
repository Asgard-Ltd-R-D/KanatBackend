using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs;
using PacketProcessing.Services.Orchestration;
using PacketProcessing.Utils.Constants;

namespace PacketProcessing.Controllers;

/// <summary>
/// Controller for managing application state (Realtime/Playback).
/// </summary>
[ApiController]
[Route("api/v1/[controller]")]
public class StateController : ControllerBase
{
    private readonly ILogger<StateController> _logger;
    private readonly IPipelineOrchestrator _orchestrator;

    public StateController(
        ILogger<StateController> logger,
        IPipelineOrchestrator orchestrator)
    {
        _logger = logger;
        _orchestrator = orchestrator;
    }

    /// <summary>
    /// Changes the application state between Realtime and Playback modes.
    /// </summary>
    /// <param name="state">The target state (realtime or playback)</param>
    [HttpPut("{state}")]
    public ActionResult<ResponseResult> ChangeState(string state)
    {
        try
        {
            // Parse the state
            if (!Enum.TryParse<States>(state, true, out var targetState))
            {
                var errorMessage = $"Invalid state: {state}. Valid states are: Realtime, Playback";
                return BadRequest(ResponseResult.ErrorResult(errorMessage));
            }

            var currentState = _orchestrator.GetCurrentState();
            
            // Check if already in the target state
            if (currentState == targetState)
            {
                return Ok(ResponseResult.SuccessResult());
            }

            // Validate the state transition
            var validationResult = ValidateStateTransition(currentState, targetState);
            if (!validationResult.IsValid)
            {
                return BadRequest(ResponseResult.ErrorResult(validationResult.ErrorMessage));
            }

            // Change the state
            _orchestrator.SetState(targetState);
            _logger.LogInformation("State changed from {CurrentState} to {NewState}", currentState, targetState);
            
            return Ok(ResponseResult.SuccessResult());
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to change state to {State}", state);
            return StatusCode(500, ResponseResult.ServerErrorResult($"Failed to change state: {ex.Message}"));
        }
    }

    /// <summary>
    /// Gets the current application state.
    /// </summary>
    [HttpGet]
    public ActionResult<ResponseResult<string>> GetState()
    {
        try
        {
            var currentState = _orchestrator.GetCurrentState();
            return Ok(ResponseResult<string>.SuccessResult(currentState.ToString()));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get current state");
            return StatusCode(500, ResponseResult<string>.ServerErrorResult("Failed to get current state"));
        }
    }

    private (bool IsValid, string ErrorMessage) ValidateStateTransition(States currentState, States targetState)
    {
        // Validate Realtime to Playback transition
        if (currentState == States.Realtime && targetState == States.Playback)
        {
            var telemetry = _orchestrator.GetStats();
            if (telemetry.Captured > 0 && telemetry.Captured > telemetry.Flushed)
            {
                return (false, "Cannot switch to Playback mode while capture may be active. Please ensure capture is stopped.");
            }
        }
        
        // TODO: Add validation for Playback to Realtime when playback is implemented
        
        return (true, string.Empty);
    }
}

