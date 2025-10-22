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
using PacketProcessing.Utils.Mappers;

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

    public async Task<RangeDto> CreateRangeAsync(RangeDto dto)
    {
        try
        {
            var repository = _efFactory.Get<RangeEntity>();
            
            // Create entity with auto-generated ID and timestamp
            var entity = new RangeEntity
            {
                Id = Guid.NewGuid(),
                Timestamp = DateTime.UtcNow,
                Start = dto.Start,
                End = dto.End,
                Description = dto.Description.Trim()
            };

            var createdEntity = await repository.AddAsync(entity);
            _logger.LogInformation("Created range with ID {Id}", createdEntity.Id);

            return RangeMapper.ToDto(createdEntity);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error creating range");
            throw;
        }
    }

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

            return RangeMapper.ToDto(range);
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
            var normalized = new PaginationParameters { Page = page, PageSize = pageSize }.Normalize();

            var result = await repository.GetPaginatedAsync(normalized.Page, normalized.PageSize);

            var dtoItems = result.Items.Select(RangeMapper.ToDto);

            return PaginatedResult<RangeDto>.Create(dtoItems, result.Page, result.PageSize, result.TotalCount);
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
            
            var dtos = ranges.Select(RangeMapper.ToDto);

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

            if (dto.Start != existingRange.Start) existingRange.Start = dto.Start;
            if (dto.End != existingRange.End) existingRange.End = dto.End;
            if (dto.Description != existingRange.Description) existingRange.Description = dto.Description;

            await repository.UpdateAsync(existingRange);
            
            _logger.LogInformation("Range {Id} updated successfully", id);

            return RangeMapper.ToDto(existingRange);
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

    public object GetCurrentModeStatus()
    {
        return _currentMode switch
        {
            States.Realtime => Realtime.GetStats(),
            States.Playback => new { Message = "Playback functionality coming soon", CurrentMode = _currentMode.ToString() },
            _ => throw new InvalidOperationException($"Unknown mode: {_currentMode}")
        };
    }

    public void ResetCurrentModeStatistics()
    {
        switch (_currentMode)
        {
            case States.Realtime:
                Realtime.ResetStats();
                _logger.LogInformation("Statistics reset requested for Realtime mode");
                break;
            case States.Playback:
                _logger.LogInformation("Statistics reset requested for Playback mode (not implemented)");
                break;
            default:
                throw new InvalidOperationException($"Unknown mode: {_currentMode}");
        }
    }

    #endregion
}
