using PacketProcessing.DTOs;
using PacketProcessing.DTOs.Range;
using PacketProcessing.Services.Playback;
using PacketProcessing.Services.Realtime;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Services;

/// <summary>
/// Range service that provides access to real-time and playback services,
/// manages application mode, and provides range entity operations
/// </summary>
public interface IRangeService
{
    /// <summary>
    /// Get the real-time service
    /// </summary>
    IRealtimeService Realtime { get; }
    
    /// <summary>
    /// Get the playback service
    /// </summary>
    IPlaybackService Playback { get; }
    
    /// <summary>
    /// Get current application mode
    /// </summary>
    States CurrentMode { get; }
    
    /// <summary>
    /// Set application mode
    /// </summary>
    void SetMode(States mode);
    
    // Range Operations
    
    /// <summary>
    /// Gets a range by ID
    /// </summary>
    /// <param name="id">The range ID</param>
    /// <returns>The range DTO if found, null otherwise</returns>
    Task<RangeDto?> GetRangeByIdAsync(Guid id);
    
    /// <summary>
    /// Gets all ranges with pagination
    /// </summary>
    /// <param name="page">Page number (1-based)</param>
    /// <param name="pageSize">Number of items per page</param>
    /// <returns>Paginated result of range DTOs</returns>
    Task<PaginatedResult<RangeDto>> GetAllRangesPaginatedAsync(int page, int pageSize);
    
    /// <summary>
    /// Gets all ranges (Development only)
    /// </summary>
    /// <returns>Collection of all range DTOs</returns>
    Task<IEnumerable<RangeDto>> GetAllRangesAsync();
    
    /// <summary>
    /// Updates a range by ID
    /// </summary>
    /// <param name="id">The range ID</param>
    /// <param name="dto">The updated range data</param>
    /// <returns>The updated range DTO if successful, null if not found</returns>
    Task<RangeDto?> UpdateRangeByIdAsync(Guid id, RangeDto dto);
    
    /// <summary>
    /// Deletes a range by ID
    /// </summary>
    /// <param name="id">The range ID</param>
    /// <returns>True if deleted, false if not found</returns>
    Task<bool> DeleteRangeByIdAsync(Guid id);
    
    /// <summary>
    /// Deletes all ranges (Development only)
    /// </summary>
    /// <returns>Number of ranges deleted</returns>
    Task<int> DeleteAllRangesAsync();
    
    /// <summary>
    /// Clears packets within a time range
    /// </summary>
    /// <param name="start">Start timestamp</param>
    /// <param name="end">End timestamp</param>
    /// <returns>Result message</returns>
    Task<bool> ClearPacketsAsync(DateTime start, DateTime end);
}

