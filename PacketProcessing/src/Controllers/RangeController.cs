using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using PacketProcessing.Config;
using PacketProcessing.DTOs;
using PacketProcessing.DTOs.Range;
using PacketProcessing.Services;
using Microsoft.AspNetCore.Http;

namespace PacketProcessing.Controllers;

/// <summary>
/// Controller for managing range operations including mode control, capture, playback, and range entity management.
/// </summary>
[ApiController]
[Route("api/range")]
public class RangeController : ControllerBase
{
    private readonly ILogger<RangeController> _logger;
    private readonly IRangeService _rangeService;

    public RangeController(
        ILogger<RangeController> logger,
        IRangeService rangeService)
    {
        _logger = logger;
        _rangeService = rangeService;
    }

    #region Range Entity Management

    /// <summary>
    /// Creates a new range.
    /// </summary>
    /// <param name="dto">The range data to create</param>
    [HttpPost("ranges")]
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult<RangeDto>))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult<RangeDto>))]
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
    /// Gets a range by ID.
    /// </summary>
    /// <param name="id">The range ID</param>
    [HttpGet("ranges/{id}")]
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult<RangeDto>))]
    [ProducesResponseType(StatusCodes.Status404NotFound, Type = typeof(ResponseResult<RangeDto>))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult<RangeDto>))]
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
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult<PaginatedResult<RangeDto>>))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult<PaginatedResult<RangeDto>>))]
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
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult<IEnumerable<RangeDto>>))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult<IEnumerable<RangeDto>>))]
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
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult<RangeDto>))]
    [ProducesResponseType(StatusCodes.Status404NotFound, Type = typeof(ResponseResult<RangeDto>))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult<RangeDto>))]
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
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult))]
    [ProducesResponseType(StatusCodes.Status404NotFound, Type = typeof(ResponseResult))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult))]
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
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult<int>))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult<int>))]
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
    [ProducesResponseType(StatusCodes.Status200OK, Type = typeof(ResponseResult<string>))]
    [ProducesResponseType(StatusCodes.Status400BadRequest, Type = typeof(ResponseResult<string>))]
    [ProducesResponseType(StatusCodes.Status500InternalServerError, Type = typeof(ResponseResult<string>))]
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

