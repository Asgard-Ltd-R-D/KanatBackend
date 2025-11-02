using System.Runtime.CompilerServices;
using Microsoft.Extensions.Configuration;
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
using PacketProcessing.Utils.ModelValidator;

namespace PacketProcessing.Services;

/// <summary>
/// Range service that provides access to real-time and playback services,
/// manages application mode, and provides range entity operations
/// </summary>
public class RangeService : IRangeService
{
    private readonly ILogger<RangeService> _logger;

    #region Services
    public IRealtimeService Realtime { get; }
    public IPlaybackService Playback { get; }
    private States _currentMode = States.Realtime;
    private readonly object _modeLock = new();

    private readonly IConfiguration _configuration;
    private readonly IInfluxRepositoryFactory _influxFactory;
    private readonly IEfRepositoryFactory _efFactory;

    public RangeService(
        ILogger<RangeService> logger,
        IRealtimeService realtimeService,
        IPlaybackService playbackService,
        IConfiguration configuration,
        IInfluxRepositoryFactory influxFactory,
        IEfRepositoryFactory efFactory)
    {
        _logger = logger;
        Realtime = realtimeService;
        Playback = playbackService;
        _configuration = configuration;
        _influxFactory = influxFactory;
        _efFactory = efFactory;
        
        _logger.LogInformation("RangeService initialized with mode: {Mode}", _currentMode);
    }

    #endregion

    #region Mode Management
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
                if (previousMode == States.Realtime && Realtime.IsActive) 
                {
                    throw new InvalidOperationException("Cannot change to Realtime mode while the realtime service is active");
                }
                
                _currentMode = mode;
                _logger.LogInformation(
                    "Application mode changed: {PreviousMode} → {NewMode}",
                    previousMode, mode);
            }
        }
    }
    #endregion

    #region Realtime Orchestration

    public async Task<RangeDto> StartRealtimeRangeAsync(CancellationToken cancellationToken, RangeDto range)
    {
        try 
        {
            // Validate and hydrate provided config (ignore Id/Timestamp/StartTime/EndTime from request)
            var availableDevices = GetAvailableDeviceNames();
            var validatedRange = RangeModelValidator.ValidateAndHydrate(range, availableDevices, _configuration);
            if (validatedRange.Config?.BpfConfig == null)
            {
                throw new InvalidOperationException("Range configuration is invalid");
            }

            // Set StartTime to current timestamp before creating range
            validatedRange.StartTime = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

            // Truncate base tables before starting a new range
            try
            {
                var motionRepo = _influxFactory.Get<MotionPacketEntity>();
                var safetyRepo = _influxFactory.Get<SafetyPacketEntity>();
                var onvifRepo = _influxFactory.Get<OnVIFPacketEntity>();
                
                await motionRepo.ClearAllPacketsAsync();
                await safetyRepo.ClearAllPacketsAsync();
                await onvifRepo.ClearAllPacketsAsync();
                
                _logger.LogInformation("Cleared base tables before starting new range");
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to clear base tables before starting range");
                // Don't fail the start operation if packet clearing fails
            }

            var createdDto = await CreateRangeAsync(validatedRange);

            createdDto.Config = validatedRange.Config;
            await Realtime.SetCurrentRangeAsync(createdDto);

            // Start realtime using hydrated configuration
            await Realtime.StartAsync(cancellationToken, createdDto.Config!.BpfConfig!);

            _logger.LogInformation("Realtime range started (Id={Id}, Device={Device})", createdDto.Id, createdDto.Config!.BpfConfig!.Device);
            return createdDto;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error starting realtime range");
            throw;
        }
    }

    public async Task<RangeDto?> StopRealtimeRangeAsync(CancellationToken cancellationToken)
    {
        try 
        {
            var currentRange = await Realtime.GetCurrentRangeAsync();

            await Realtime.StopAsync(cancellationToken);

            // Reset runtime stats/values per request
            Realtime.ResetStats();

            if (currentRange != null)
            {
                currentRange.EndTime = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                var updated = await UpdateRangeByIdAsync(currentRange.Id, currentRange);
                if (updated == null)
                {
                    _logger.LogWarning("Range {Id} not found during stop update", currentRange.Id);
                }
                else
                {
                    // Reflect updated DTO in realtime service state
                    await Realtime.SetCurrentRangeAsync(updated);
                    currentRange = updated;
                }

                // Create session tables for the range
                try
                {
                    var motionRepo = _influxFactory.Get<MotionPacketEntity>();
                    var safetyRepo = _influxFactory.Get<SafetyPacketEntity>();
                    var onvifRepo = _influxFactory.Get<OnVIFPacketEntity>();
                    
                    await motionRepo.CreateSessionTableAsync(currentRange.Id);
                    await safetyRepo.CreateSessionTableAsync(currentRange.Id);
                    await onvifRepo.CreateSessionTableAsync(currentRange.Id);
                    
                    _logger.LogInformation("Created session tables for range {Id}", currentRange.Id);
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Failed to create session tables for range {Id}", currentRange.Id);
                    // Don't fail the stop operation if session table creation fails
                }

                // Clear all packets from base tables
                try
                {
                    var motionRepo = _influxFactory.Get<MotionPacketEntity>();
                    var safetyRepo = _influxFactory.Get<SafetyPacketEntity>();
                    var onvifRepo = _influxFactory.Get<OnVIFPacketEntity>();
                    
                    await motionRepo.ClearAllPacketsAsync();
                    await safetyRepo.ClearAllPacketsAsync();
                    await onvifRepo.ClearAllPacketsAsync();
                    
                    _logger.LogInformation("Cleared all packets from base tables after range {Id}", currentRange.Id);
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Failed to clear packets for range {Id}", currentRange.Id);
                    // Don't fail the stop operation if packet clearing fails
                }
            }

            _logger.LogInformation("Realtime range stopped (Id={Id})", currentRange?.Id);
            return currentRange;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error stopping realtime range");
            throw;
        }
    }

    public ICollection<string> GetAvailableDeviceNames()
    {
        return Realtime.GetAvailableDeviceNames();
    }
    
    #endregion

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
                Description = dto.Description.Trim(),
                StartTime = dto.StartTime,
                EndTime = -1,
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

            if (dto.StartTime != existingRange.StartTime) existingRange.StartTime = dto.StartTime;
            if (dto.EndTime != existingRange.EndTime) existingRange.EndTime = dto.EndTime;
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
            var range = await repository.GetByIdAsync(id);

            if (range == null)
            {
                _logger.LogDebug("Range with ID {Id} not found for deletion", id);
                return false;
            }

            // Delete session tables for all packet types before deleting the range entity
            try
            {
                var motionRepo = _influxFactory.Get<MotionPacketEntity>();
                var safetyRepo = _influxFactory.Get<SafetyPacketEntity>();
                var onvifRepo = _influxFactory.Get<OnVIFPacketEntity>();
                
                await motionRepo.DeletePacketsByRangeAsync(id);
                await safetyRepo.DeletePacketsByRangeAsync(id);
                await onvifRepo.DeletePacketsByRangeAsync(id);
                
                _logger.LogInformation("Deleted session tables for range {Id}", id);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to delete session tables for range {Id}", id);
                // Continue with range deletion even if session table deletion fails
            }

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
            _logger.LogInformation("Clear all packets requested");
            
            var motionRepo = _influxFactory.Get<MotionPacketEntity>();
            var safetyRepo = _influxFactory.Get<SafetyPacketEntity>();
            var onvifRepo = _influxFactory.Get<OnVIFPacketEntity>();
            await motionRepo.ClearAllPacketsAsync();
            await safetyRepo.ClearAllPacketsAsync();
            await onvifRepo.ClearAllPacketsAsync();
            
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error clearing all packets");
            throw;
        }
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
