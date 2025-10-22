using Microsoft.Extensions.Logging;
using PacketProcessing.DTOs;
using PacketProcessing.DTOs.Range;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Entities.Range;
using PacketProcessing.Repositories.EfRepository;
using PacketProcessing.Repositories.InfluxRepository;
using PacketProcessing.Services.Playback;
using PacketProcessing.Services.Realtime;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Services;

/// <summary>
/// Range service that provides access to real-time and playback services,
/// manages application mode, and provides range entity operations
/// </summary>
public class RangeService : IRangeService
{
    private readonly ILogger<RangeService> _logger;
    private States _currentMode = States.Realtime;
    private readonly object _modeLock = new();
    
    private readonly IInfluxRepositoryFactory _influxFactory;
    private readonly IEfRepositoryFactory _efFactory;

    public RangeService(
        ILogger<RangeService> logger,
        IRealtimeService realtimeService,
        IPlaybackService playbackService,
        IInfluxRepositoryFactory influxFactory,
        IEfRepositoryFactory efFactory)
    {
        _logger = logger;
        Realtime = realtimeService;
        Playback = playbackService;
        _influxFactory = influxFactory;
        _efFactory = efFactory;
        
        _logger.LogInformation("RangeService initialized with mode: {Mode}", _currentMode);
    }

    public IRealtimeService Realtime { get; }
    
    public IPlaybackService Playback { get; }

    public States CurrentMode
    {
        get
        {
            lock (_modeLock)
            {
                return _currentMode;
            }
        }
    }

    public void SetMode(States mode)
    {
        lock (_modeLock)
        {
            var previousMode = _currentMode;
            
            if (previousMode != mode)
            {
                _currentMode = mode;
                _logger.LogInformation(
                    "Application mode changed: {PreviousMode} → {NewMode}",
                    previousMode, mode);
            }
        }
    }

    #region Range Operations

    public async Task<RangeDto?> GetRangeByIdAsync(Guid id)
    {
        try
        {
            var repository = _efFactory.Get<RangeEntity>();
            var range = await repository.GetByIdAsync(id);
            
            if (range == null)
            {
                _logger.LogDebug("Range with ID {Id} not found", id);
                return null;
            }

            return new RangeDto
            {
                Id = range.Id,
                Timestamp = range.Timestamp,
                Start = range.Start,
                End = range.End,
                Description = range.Description
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error getting range by ID {Id}", id);
            throw;
        }
    }

    public async Task<PaginatedResult<RangeDto>> GetAllRangesPaginatedAsync(int page, int pageSize)
    {
        try
        {
            var repository = _efFactory.Get<RangeEntity>();
            var pagination = new PaginationParameters { Page = page, PageSize = pageSize }.Normalize();
            
            var ranges = await repository.GetAllAsync(
                skip: pagination.GetSkip(), 
                take: pagination.GetTake());
            
            var totalCount = await repository.CountAsync();
            
            var dtos = ranges.Select(r => new RangeDto
            {
                Id = r.Id,
                Timestamp = r.Timestamp,
                Start = r.Start,
                End = r.End,
                Description = r.Description
            });

            return PaginatedResult<RangeDto>.Create(
                dtos, 
                pagination.Page, 
                pagination.PageSize, 
                totalCount);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error getting paginated ranges (page: {Page}, pageSize: {PageSize})", page, pageSize);
            throw;
        }
    }

    public async Task<IEnumerable<RangeDto>> GetAllRangesAsync()
    {
        try
        {
            var repository = _efFactory.Get<RangeEntity>();
            var ranges = await repository.GetAllAsync();
            
            var dtos = ranges.Select(r => new RangeDto
            {
                Id = r.Id,
                Timestamp = r.Timestamp,
                Start = r.Start,
                End = r.End,
                Description = r.Description
            });

            _logger.LogDebug("Retrieved {Count} ranges", dtos.Count());
            return dtos;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error getting all ranges");
            throw;
        }
    }

    public async Task<RangeDto?> UpdateRangeByIdAsync(Guid id, RangeDto dto)
    {
        try
        {
            var repository = _efFactory.Get<RangeEntity>();
            var existingRange = await repository.GetByIdAsync(id);
            
            if (existingRange == null)
            {
                _logger.LogDebug("Range with ID {Id} not found for update", id);
                return null;
            }

            existingRange.Start = dto.Start;
            existingRange.End = dto.End;
            existingRange.Description = dto.Description;

            await repository.UpdateAsync(existingRange);
            
            _logger.LogInformation("Range {Id} updated successfully", id);

            return new RangeDto
            {
                Id = existingRange.Id,
                Timestamp = existingRange.Timestamp,
                Start = existingRange.Start,
                End = existingRange.End,
                Description = existingRange.Description
            };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error updating range {Id}", id);
            throw;
        }
    }

    public async Task<bool> DeleteRangeByIdAsync(Guid id)
    {
        try
        {
            var repository = _efFactory.Get<RangeEntity>();
            var result = await repository.DeleteAsync(id);
            
            if (result)
            {
                _logger.LogInformation("Range {Id} deleted successfully", id);
            }
            else
            {
                _logger.LogDebug("Range with ID {Id} not found for deletion", id);
            }
            
            return result;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error deleting range {Id}", id);
            throw;
        }
    }

    public async Task<int> DeleteAllRangesAsync()
    {
        try
        {
            var repository = _efFactory.Get<RangeEntity>();
            var ranges = await repository.GetAllAsync();
            var count = 0;
            
            foreach (var range in ranges)
            {
                var deleted = await repository.DeleteAsync(range.Id);
                if (deleted) count++;
            }
            
            _logger.LogWarning("Deleted {Count} ranges via DeleteAllRangesAsync", count);
            return count;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error deleting all ranges");
            throw;
        }
    }

    public async Task<bool> ClearPacketsAsync(DateTime start, DateTime end)
    {
        try
        {
            // Normalize to UTC for QuestDB
            var startUtc = start.Kind == DateTimeKind.Utc ? start : DateTime.SpecifyKind(start, DateTimeKind.Utc);
            var endUtc = end.Kind == DateTimeKind.Utc ? end : DateTime.SpecifyKind(end, DateTimeKind.Utc);

            _logger.LogInformation("Clear packets requested for range {Start:u} to {End:u}", startUtc, endUtc);
            
            var motionRepo = _influxFactory.Get<MotionPacketEntity>();
            var safetyRepo = _influxFactory.Get<SafetyPacketEntity>();
            var onvifRepo = _influxFactory.Get<OnVIFPacketEntity>();
            await motionRepo.ClearPacketsByRangeAsync(startUtc, endUtc);
            await safetyRepo.ClearPacketsByRangeAsync(startUtc, endUtc);
            await onvifRepo.ClearPacketsByRangeAsync(startUtc, endUtc);
            
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error clearing packets for range {Start} to {End}", start, end);
            throw;
        }
    }

    #endregion
}
