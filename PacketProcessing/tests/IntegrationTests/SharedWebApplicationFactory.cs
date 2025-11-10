using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Hosting;
using PacketProcessing.Config;
using PacketProcessing.Services;
using Microsoft.Extensions.Configuration;
using Microsoft.EntityFrameworkCore;
using PacketProcessing.DTOs;
using PacketProcessing.DTOs.Range;
using PacketProcessing.DTOs.Conf;
using PacketProcessing.DTOs.Stream;
using PacketProcessing.Services.Playback;
using PacketProcessing.Services.Realtime;
using PacketProcessing.Services.Transmission;
using PacketProcessing.Utils.Enums;
using PacketProcessing.Entities;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories.InfluxRepository;
using QuestDB.Senders;

namespace PacketProcessing.IntegrationTests;

/// <summary>
/// Shared WebApplicationFactory for integration tests to avoid creating multiple instances
/// </summary>
public class SharedWebApplicationFactory : WebApplicationFactory<ConfigurationInjection>
{
    private bool _disposed;
    
    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.ConfigureServices(services =>
        {
            // Remove the real database contexts
            var dbContextDescriptor = services.SingleOrDefault(
                d => d.ServiceType == typeof(DbContextOptions<Context.PostgresDbContext>));
            if (dbContextDescriptor != null)
                services.Remove(dbContextDescriptor);

            // Remove QuestDbContext registration if it exists
            var questDbContextDescriptor = services.SingleOrDefault(
                d => d.ServiceType == typeof(Context.QuestDbContext));
            if (questDbContextDescriptor != null)
                services.Remove(questDbContextDescriptor);

            // Add in-memory database for testing
            services.AddDbContext<Context.PostgresDbContext>(options =>
            {
                options.UseInMemoryDatabase("TestPostgresDb");
            });

            // Register QuestDbContext for integration tests
            services.AddSingleton<Context.QuestDbContext>(provider =>
            {
                var configuration = provider.GetRequiredService<IConfiguration>();
                var logger = provider.GetRequiredService<ILogger<Context.QuestDbContext>>();
                return new Context.QuestDbContext(configuration, logger);
            });

            // Configure test-specific services
            ConfigureTestServices(services);
        });

        builder.UseEnvironment("Test");
        builder.ConfigureLogging(logging =>
        {
            logging.ClearProviders();
            logging.SetMinimumLevel(LogLevel.Warning);
        });
        
        // Configure test-specific configuration
        builder.ConfigureAppConfiguration(config =>
        {
            config.AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["SkipDatabaseInitialization"] = "true"
            });
        });
    }

    protected virtual void ConfigureTestServices(IServiceCollection services)
    {
        services.RemoveAll<IHostedService>();
        services.RemoveAll<IInfluxRepositoryFactory>();
        services.RemoveAll(typeof(IInfluxRepository<>));
        services.RemoveAll<IRangeService>();
        services.RemoveAll<IRealtimeService>();
        services.RemoveAll<IPlaybackService>();

        services.AddSingleton(typeof(IInfluxRepository<>), typeof(StubInfluxRepository<>));
        services.AddSingleton<IInfluxRepositoryFactory, StubInfluxRepositoryFactory>();
        services.AddSingleton<RealtimeStub>();
        services.AddSingleton<IRealtimeService>(sp => sp.GetRequiredService<RealtimeStub>());
        services.AddSingleton<PlaybackStub>();
        services.AddSingleton<IPlaybackService>(sp => sp.GetRequiredService<PlaybackStub>());
        services.AddSingleton<RangeServiceStub>();
        services.AddSingleton<IRangeService>(sp => sp.GetRequiredService<RangeServiceStub>());
    }

    public override async ValueTask DisposeAsync()
    {
        if (!_disposed)
        {
            _disposed = true;
        }
        
        await base.DisposeAsync();
    }

    private sealed class RangeServiceStub : IRangeService
    {
        private readonly IDictionary<Guid, RangeDto> _ranges = new Dictionary<Guid, RangeDto>();
        private readonly IRealtimeService _realtime;
        private readonly IPlaybackService _playback;
        private States _currentMode = States.Realtime;

        public RangeServiceStub(IRealtimeService realtime, IPlaybackService playback)
        {
            _realtime = realtime;
            _playback = playback;
        }

        public IRealtimeService Realtime => _realtime;
        public IPlaybackService Playback => _playback;
        public States CurrentMode => _currentMode;

        public void SetMode(States mode)
        {
            _currentMode = mode;
        }

        public Task<RangeDto> StartRealtimeRangeAsync(CancellationToken cancellationToken, RangeDto range)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var created = EnsureRange(range);
            _realtime.ResetStats();
            return Task.FromResult(created);
        }

        public Task<RangeDto?> StopRealtimeRangeAsync(CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            _realtime.ResetStats();
            return Task.FromResult<RangeDto?>(null);
        }

        public ICollection<string> GetAvailableDeviceNames()
        {
            return _realtime.GetAvailableDeviceNames();
        }

        public Task<RangeDto> CreateRangeAsync(RangeDto dto)
        {
            var created = EnsureRange(dto);
            return Task.FromResult(created);
        }

        public Task<RangeDto?> GetRangeByIdAsync(Guid id)
        {
            _ranges.TryGetValue(id, out var dto);
            return Task.FromResult(dto);
        }

        public Task<PaginatedResult<RangeDto>> GetAllRangesPaginatedAsync(int page, int pageSize)
        {
            var normalizedPage = Math.Max(1, page);
            var normalizedSize = Math.Max(1, pageSize);

            var items = _ranges.Values
                .OrderBy(r => r.Timestamp)
                .Skip((normalizedPage - 1) * normalizedSize)
                .Take(normalizedSize)
                .ToList();

            var total = _ranges.Count;
            var result = PaginatedResult<RangeDto>.Create(items, normalizedPage, normalizedSize, total);
            return Task.FromResult(result);
        }

        public Task<IEnumerable<RangeDto>> GetAllRangesAsync()
        {
            return Task.FromResult<IEnumerable<RangeDto>>(_ranges.Values.ToList());
        }

        public Task<RangeDto?> UpdateRangeByIdAsync(Guid id, RangeDto dto)
        {
            if (!_ranges.TryGetValue(id, out var existing))
            {
                return Task.FromResult<RangeDto?>(null);
            }

            existing.Description = dto.Description;
            existing.StartTime = dto.StartTime;
            existing.EndTime = dto.EndTime;
            existing.Config = dto.Config;
            return Task.FromResult<RangeDto?>(existing);
        }

        public Task<bool> DeleteRangeByIdAsync(Guid id)
        {
            var removed = _ranges.Remove(id);
            return Task.FromResult(removed);
        }

        public Task<int> DeleteAllRangesAsync()
        {
            var count = _ranges.Count;
            _ranges.Clear();
            return Task.FromResult(count);
        }

        public Task<bool> ClearPacketsAsync(DateTime start, DateTime end)
        {
            return Task.FromResult(true);
        }

        public void ResetCurrentModeStatistics()
        {
            _realtime.ResetStats();
        }

        private RangeDto EnsureRange(RangeDto dto)
        {
            var id = dto.Id != Guid.Empty ? dto.Id : Guid.NewGuid();
            var range = new RangeDto
            {
                Id = id,
                Timestamp = dto.Timestamp == default ? DateTime.UtcNow : dto.Timestamp,
                Description = dto.Description,
                StartTime = dto.StartTime,
                EndTime = dto.EndTime,
                Config = dto.Config
            };

            _ranges[id] = range;
            return range;
        }
    }

    private sealed class RealtimeStub : IRealtimeService
    {
        private RangeDto? _currentRange;
        private readonly List<string> _deviceNames = new() { "eth0", "eth1" };

        public bool IsActive { get; private set; }

        public Task StartAsync(CancellationToken cancellationToken, BPFConfDto config)
        {
            cancellationToken.ThrowIfCancellationRequested();
            IsActive = true;
            return Task.CompletedTask;
        }

        public Task StartAsync(CancellationToken cancellationToken, string deviceName)
        {
            cancellationToken.ThrowIfCancellationRequested();
            IsActive = true;
            return Task.CompletedTask;
        }

        public Task StopAsync(CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            IsActive = false;
            return Task.CompletedTask;
        }

        public Task<RangeDto?> GetCurrentRangeAsync()
        {
            return Task.FromResult(_currentRange);
        }

        public Task SetCurrentRangeAsync(RangeDto range)
        {
            _currentRange = range;
            return Task.CompletedTask;
        }

        public void ResetStats()
        {
        }

        public TelemetryDto GetStats()
        {
            return new TelemetryDto();
        }

        public ICollection<string> GetAvailableDeviceNames()
        {
            return _deviceNames;
        }
    }

    private sealed class PlaybackStub : IPlaybackService
    {
        private readonly List<StreamRequestDto> _active = new();

        public Task StartPlaybackAsync(StreamRequestDto request)
        {
            _active.Add(request);
            return Task.CompletedTask;
        }

        public Task StopPlaybackAsync(StreamRequestDto request)
        {
            _active.RemoveAll(r => r.Equals(request));
            return Task.CompletedTask;
        }

        public Task StopAllPlaybacksAsync()
        {
            _active.Clear();
            return Task.CompletedTask;
        }

        public ICollection<StreamRequestDto> GetActivePlaybacks()
        {
            return _active;
        }
    }

    protected override void Dispose(bool disposing)
    {
        if (!_disposed)
        {
            _disposed = true;
        }
        base.Dispose(disposing);
    }

    private sealed class StubInfluxRepositoryFactory : IInfluxRepositoryFactory
    {
        private readonly IServiceProvider _serviceProvider;

        public StubInfluxRepositoryFactory(IServiceProvider serviceProvider)
        {
            _serviceProvider = serviceProvider;
        }

        public IInfluxRepository<T> Get<T>() where T : BasePacketEntity
        {
            return (IInfluxRepository<T>)_serviceProvider.GetRequiredService(typeof(IInfluxRepository<T>));
        }
    }

    private sealed class StubInfluxRepository<T> : IInfluxRepository<T> where T : BasePacketEntity
    {
        public Task WriteQuestDbAsync(ISender sender, T entity, CancellationToken ct = default) => Task.CompletedTask;

        public Task WriteBatchQuestDbAsync(ISender sender, IReadOnlyList<T> batch, CancellationToken ct = default) => Task.CompletedTask;

        public Task ClearAllPacketsAsync() => Task.CompletedTask;

        public Task<IEnumerable<T>> GetAllPacketsByRangeAsync(Guid rangeId) =>
            Task.FromResult<IEnumerable<T>>(Array.Empty<T>());

        public Task<IEnumerable<T>> GetPaginatedPacketsByRangeAsync(Guid rangeId, DateTime startTimestamp, DateTime endTimestamp, PacketProcessing.Utils.Enums.OrderBy orderBy = PacketProcessing.Utils.Enums.OrderBy.Asc, int page = 1, int pageSize = 1000) =>
            Task.FromResult<IEnumerable<T>>(Array.Empty<T>());

        public Task<IEnumerable<T>> GetPaginatedPacketsByRangeAsyncWithInterval(Guid rangeId, DateTime startTimestamp, DateTime endTimestamp, int interval, PacketProcessing.Utils.Enums.OrderBy orderBy = PacketProcessing.Utils.Enums.OrderBy.Asc, int page = 1, int pageSize = 1000) =>
            Task.FromResult<IEnumerable<T>>(Array.Empty<T>());

        public Task DeletePacketsByRangeAsync(Guid rangeId) => Task.CompletedTask;

        public Task CreateSessionTableAsync(Guid rangeId) => Task.CompletedTask;
    }
}

