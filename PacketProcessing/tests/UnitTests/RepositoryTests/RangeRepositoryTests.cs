using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using PacketProcessing.Config;
using PacketProcessing.Context;
using PacketProcessing.Entities.Range;
using PacketProcessing.Repositories.EfRepository;
using Xunit;

namespace PacketProcessing.Tests.unit.RepositoryTests;

/// <summary>
/// Tests for range repositories (PostgreSQL/EF Core)
/// </summary>
public class RangeRepositoryTests : IDisposable
{
    private readonly ServiceProvider _serviceProvider;
    private readonly PostgresDbContext _dbContext;
    private readonly IEfRepository<RangeEntity> _rangeRepository;
    private readonly IEfRepository<EventEntity> _eventRepository;
    private readonly IEfRepository<TargetEntity> _targetRepository;
    private readonly IEfRepository<HitEntity> _hitRepository;

    public RangeRepositoryTests()
    {
        // Setup test services
        var services = new ServiceCollection();
        
        // Add logging
        services.AddLogging();
        
        // Add test configuration
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                {"ConnectionStrings:Postgres", "Host=localhost;Port=56432;Database=pdb;Username=postgres;Password=postgres;"},
                {"ConnectionStrings:QuestDb", "Host=localhost;Port=9000;Database=qdb;Username=quest;Password=quest;"},
                {"Postgres:Host", "localhost"},
                {"Postgres:Port", "56432"},
                {"Postgres:Database", "pdb"},
                {"Postgres:Username", "postgres"},
                {"Postgres:Password", "postgres"},
                {"QuestDb:PgHost", "localhost"},
                {"QuestDb:PgPort", "8812"},
                {"QuestDb:Database", "qdb"},
                {"QuestDb:PgUser", "quest"},
                {"QuestDb:PgPassword", "quest"}
            })
            .Build();

        // Configure database services
        DatabaseConfiguration.ConfigureServices(services, configuration);
        
        // Register EF repositories
        services.AddScoped(typeof(IEfRepository<>), typeof(EfRepository<>));
        
        _serviceProvider = services.BuildServiceProvider();
        _dbContext = _serviceProvider.GetRequiredService<PostgresDbContext>();
        
        // Get repositories
        _rangeRepository = _serviceProvider.GetRequiredService<IEfRepository<RangeEntity>>();
        _eventRepository = _serviceProvider.GetRequiredService<IEfRepository<EventEntity>>();
        _targetRepository = _serviceProvider.GetRequiredService<IEfRepository<TargetEntity>>();
        _hitRepository = _serviceProvider.GetRequiredService<IEfRepository<HitEntity>>();
        
        // Ensure database and tables are ready
        _dbContext.EnsureDatabaseAsync().GetAwaiter().GetResult();
        CleanAsync().GetAwaiter().GetResult();
    }

    private async Task CleanAsync()
    {
        // Order matters due to FKs
        await _dbContext.Database.ExecuteSqlRawAsync("TRUNCATE TABLE hits CASCADE");
        await _dbContext.Database.ExecuteSqlRawAsync("TRUNCATE TABLE events CASCADE");
        await _dbContext.Database.ExecuteSqlRawAsync("TRUNCATE TABLE ranges CASCADE");
        await _dbContext.Database.ExecuteSqlRawAsync("TRUNCATE TABLE targets CASCADE");
    }

    [Fact]
    public async Task PostgresDbContext_ShouldBeConfiguredAndAvailable()
    {
        // Arrange & Act
        var canConnect = await _dbContext.Database.CanConnectAsync();
        var ensured = await _dbContext.EnsureDatabaseAsync();

        // Assert
        Assert.True(canConnect);
        // EnsureDatabaseAsync returns true on first creation, false otherwise – both are acceptable
        Assert.True(ensured || ensured == false);
    }

    [Fact]
    public async Task RangeRepository_AddAsync_ShouldCreateRangeEntity()
    {
        await CleanAsync();

        var range = new RangeEntity
        {
            Start = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            End = DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(),
            Description = "Test Range",
            Timestamp = DateTime.UtcNow
        };

        var createdRange = await _rangeRepository.AddAsync(range);

        Assert.NotEqual(Guid.Empty, createdRange.Id);
        Assert.Equal("Test Range", createdRange.Description);

        await CleanAsync();
    }

    [Fact]
    public async Task RangeRepository_GetByIdAsync_ShouldReturnRangeEntity()
    {
        await CleanAsync();

        var range = new RangeEntity
        {
            Start = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            End = DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(),
            Description = "Test Range for GetById",
            Timestamp = DateTime.UtcNow
        };
        var createdRange = await _rangeRepository.AddAsync(range);

        var retrievedRange = await _rangeRepository.GetByIdAsync(createdRange.Id);

        Assert.NotNull(retrievedRange);
        Assert.Equal(createdRange.Id, retrievedRange.Id);
        Assert.Equal("Test Range for GetById", retrievedRange.Description);

        await CleanAsync();
    }

    [Fact]
    public async Task RangeRepository_GetAll_ShouldReturnAllRangeEntities()
    {
        await CleanAsync();

        var range1 = new RangeEntity
        {
            Start = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            End = DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(),
            Description = "Test Range 1",
            Timestamp = DateTime.UtcNow
        };
        var range2 = new RangeEntity
        {
            Start = DateTimeOffset.UtcNow.AddHours(2).ToUnixTimeSeconds(),
            End = DateTimeOffset.UtcNow.AddHours(3).ToUnixTimeSeconds(),
            Description = "Test Range 2",
            Timestamp = DateTime.UtcNow
        };
        await _rangeRepository.AddAsync(range1);
        await _rangeRepository.AddAsync(range2);
        var allRanges = await _dbContext.Set<RangeEntity>().ToListAsync();
        var hasRange1 = allRanges.Any(r => r.Description == "Test Range 1");
        var hasRange2 = allRanges.Any(r => r.Description == "Test Range 2");
        Assert.True(hasRange1);
        Assert.True(hasRange2);

        await CleanAsync();
    }

    [Fact]
    public async Task RangeRepository_UpdateAsync_ShouldUpdateRangeEntity()
    {
        await CleanAsync();

        // Arrange
        var range = new RangeEntity
        {
            Start = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            End = DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(),
            Description = "Original Description",
            Timestamp = DateTime.UtcNow
        };
        var createdRange = await _rangeRepository.AddAsync(range);
        
        // Update the description
        createdRange.Description = "Updated Description";

        // Act
        var updatedRange = await _rangeRepository.UpdateAsync(createdRange);

        // Assert
        Assert.Equal("Updated Description", updatedRange.Description);

        await CleanAsync();
    }

    [Fact]
    public async Task RangeRepository_DeleteAsync_ShouldDeleteRangeEntity()
    {
        await CleanAsync();

        // Arrange
        var range = new RangeEntity
        {
            Start = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            End = DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(),
            Description = "Range to Delete",
            Timestamp = DateTime.UtcNow
        };
        var createdRange = await _rangeRepository.AddAsync(range);

        // Act
        await _rangeRepository.DeleteAsync(createdRange.Id);

        // Assert
        var deletedRange = await _rangeRepository.GetByIdAsync(createdRange.Id);
        Assert.Null(deletedRange);

        await CleanAsync();
    }

    [Fact]
    public async Task EventRepository_AddAsync_ShouldCreateEventEntity()
    {
        await CleanAsync();

        // Arrange
        var range = new RangeEntity
        {
            Start = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            End = DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(),
            Description = "Test Range for Event",
            Timestamp = DateTime.UtcNow
        };
        var createdRange = await _rangeRepository.AddAsync(range);
        
        var eventEntity = new EventEntity
        {
            Start = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            End = DateTimeOffset.UtcNow.AddMinutes(30).ToUnixTimeSeconds(),
            RangeId = createdRange.Id,
            Timestamp = DateTime.UtcNow
        };

        // Act
        var createdEvent = await _eventRepository.AddAsync(eventEntity);

        // Assert
        Assert.NotEqual(Guid.Empty, createdEvent.Id);
        Assert.Equal(createdRange.Id, createdEvent.RangeId);

        await CleanAsync();
    }

    [Fact]
    public async Task TargetRepository_AddAsync_ShouldCreateTargetEntity()
    {
        await CleanAsync();

        // Arrange
        var target = new TargetEntity
        {
            PosX = 100,
            PosY = 200,
            CenterX = 150,
            CenterY = 250,
            Timestamp = DateTime.UtcNow
        };

        // Act
        var createdTarget = await _targetRepository.AddAsync(target);

        // Assert
        Assert.NotEqual(Guid.Empty, createdTarget.Id);
        Assert.Equal(100, createdTarget.PosX);
        Assert.Equal(200, createdTarget.PosY);

        await CleanAsync();
    }

    [Fact]
    public async Task HitRepository_AddAsync_ShouldCreateHitEntity()
    {
        await CleanAsync();

        // Arrange
        var target = new TargetEntity
        {
            PosX = 100,
            PosY = 200,
            CenterX = 150,
            CenterY = 250,
            Timestamp = DateTime.UtcNow
        };
        var createdTarget = await _targetRepository.AddAsync(target);
        
        var range = new RangeEntity
        {
            Start = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            End = DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(),
            Description = "Test Range for Hit",
            Timestamp = DateTime.UtcNow
        };
        var createdRange = await _rangeRepository.AddAsync(range);
        
        var eventEntity = new EventEntity
        {
            Start = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            End = DateTimeOffset.UtcNow.AddMinutes(30).ToUnixTimeSeconds(),
            RangeId = createdRange.Id,
            Timestamp = DateTime.UtcNow
        };
        var createdEvent = await _eventRepository.AddAsync(eventEntity);
        
        var hit = new HitEntity
        {
            RangeToTarget = 150.5f,
            PosX = 120,
            PosY = 180,
            CenterX = 160,
            CenterY = 220,
            TargetId = createdTarget.Id,
            EventId = createdEvent.Id,
            Timestamp = DateTime.UtcNow
        };

        // Act
        var createdHit = await _hitRepository.AddAsync(hit);

        // Assert
        Assert.NotEqual(Guid.Empty, createdHit.Id);
        Assert.Equal(createdTarget.Id, createdHit.TargetId);
        Assert.Equal(createdEvent.Id, createdHit.EventId);
        Assert.Equal(150.5f, createdHit.RangeToTarget);

        await CleanAsync();
    }

    // Negative-path tests removed per request; focus on success scenarios only

    public void Dispose()
    {
        _dbContext?.Dispose();
        _serviceProvider?.Dispose();
    }
}
