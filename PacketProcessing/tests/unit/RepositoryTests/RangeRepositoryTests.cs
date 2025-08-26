using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.ChangeTracking;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using PacketProcessing.Config;
using PacketProcessing.Context;
using PacketProcessing.Entities.Range;
using PacketProcessing.Repositories;
using PacketProcessing.Tests;
using Xunit;

namespace PacketProcessing.Tests.unit.RepositoryTests;

/// <summary>
/// Tests for range repositories (PostgreSQL/EF Core)
/// </summary>
public class RangeRepositoryTests : IDisposable
{
    private readonly ServiceProvider _serviceProvider;
    private readonly AppDbContext _dbContext;
    private readonly IRangeRepository<RangeEntity> _rangeRepository;
    private readonly IRangeRepository<EventEntity> _eventRepository;
    private readonly IRangeRepository<TargetEntity> _targetRepository;
    private readonly IRangeRepository<HitEntity> _hitRepository;

    public RangeRepositoryTests()
    {
        // Setup test services
        var services = new ServiceCollection();
        
        // Add logging
        services.AddLogging(builder => builder.AddConsole());
        
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
                {"QuestDb:Host", "localhost"},
                {"QuestDb:PostgresPort", "8812"},
                {"QuestDb:Database", "qdb"},
                {"QuestDb:Username", "quest"},
                {"QuestDb:Password", "quest"}
            })
            .Build();

        // Configure database services
        DatabaseConfiguration.ConfigureServices(services, configuration);
        
        _serviceProvider = services.BuildServiceProvider();
        _dbContext = _serviceProvider.GetRequiredService<AppDbContext>();
        
        // Get repositories
        _rangeRepository = _serviceProvider.GetRequiredService<IRangeRepository<RangeEntity>>();
        _eventRepository = _serviceProvider.GetRequiredService<IRangeRepository<EventEntity>>();
        _targetRepository = _serviceProvider.GetRequiredService<IRangeRepository<TargetEntity>>();
        _hitRepository = _serviceProvider.GetRequiredService<IRangeRepository<HitEntity>>();
        
        // Ensure database is created
        _dbContext.Database.EnsureCreated();
    }

    [Fact]
    public async Task RangeRepository_AddAsync_ShouldCreateRangeEntity()
    {
        // Arrange
        var range = new RangeEntity
        {
            Start = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            End = DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(),
            Description = "Test Range",
            Timestamp = DateTime.UtcNow
        };

        // Act
        var createdRange = await _rangeRepository.AddAsync(range);

        // Assert
        var passed = createdRange.Id != Guid.Empty && createdRange.Description == "Test Range";
        
        TestResultLogger.LogTestResult(
            "RangeRepository_AddAsync_ShouldCreateRangeEntity",
            passed,
            "Range entity creation",
            "Range should be created with valid ID and description",
            $"Id={createdRange.Id}, Description={createdRange.Description}"
        );
        
        Assert.NotEqual(Guid.Empty, createdRange.Id);
        Assert.Equal("Test Range", createdRange.Description);
    }

    [Fact]
    public async Task RangeRepository_GetByIdAsync_ShouldReturnRangeEntity()
    {
        // Arrange
        var range = new RangeEntity
        {
            Start = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            End = DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(),
            Description = "Test Range for GetById",
            Timestamp = DateTime.UtcNow
        };
        var createdRange = await _rangeRepository.AddAsync(range);

        // Act
        var retrievedRange = await _rangeRepository.GetByIdAsync(createdRange.Id);

        // Assert
        var passed = retrievedRange != null && retrievedRange.Id == createdRange.Id;
        
        TestResultLogger.LogTestResult(
            "RangeRepository_GetByIdAsync_ShouldReturnRangeEntity",
            passed,
            "Range entity retrieval by ID",
            "Should return the correct range entity",
            $"Retrieved={retrievedRange != null}, Id={retrievedRange?.Id}"
        );
        
        Assert.NotNull(retrievedRange);
        Assert.Equal(createdRange.Id, retrievedRange.Id);
        Assert.Equal("Test Range for GetById", retrievedRange.Description);
    }

    [Fact]
    public async Task RangeRepository_GetAll_ShouldReturnAllRangeEntities()
    {
        // Arrange
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

        // Act - Use DbContext directly since IEfRepository doesn't have GetAll
        var allRanges = await _dbContext.Set<RangeEntity>().ToListAsync();

        // Assert
        var passed = allRanges.Any(r => r.Description == "Test Range 1") && 
                    allRanges.Any(r => r.Description == "Test Range 2");
        
        TestResultLogger.LogTestResult(
            "RangeRepository_GetAll_ShouldReturnAllRangeEntities",
            passed,
            "Range entity retrieval - all",
            "Should return all range entities",
            $"Count={allRanges.Count}, HasRange1={allRanges.Any(r => r.Description == "Test Range 1")}, HasRange2={allRanges.Any(r => r.Description == "Test Range 2")}"
        );
        
        Assert.True(allRanges.Any(r => r.Description == "Test Range 1"));
        Assert.True(allRanges.Any(r => r.Description == "Test Range 2"));
    }

    [Fact]
    public async Task RangeRepository_UpdateAsync_ShouldUpdateRangeEntity()
    {
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
        var passed = updatedRange.Description == "Updated Description";
        
        TestResultLogger.LogTestResult(
            "RangeRepository_UpdateAsync_ShouldUpdateRangeEntity",
            passed,
            "Range entity update",
            "Should update the range entity description",
            $"UpdatedDescription={updatedRange.Description}"
        );
        
        Assert.Equal("Updated Description", updatedRange.Description);
    }

    [Fact]
    public async Task RangeRepository_DeleteAsync_ShouldDeleteRangeEntity()
    {
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
        var passed = deletedRange == null;
        
        TestResultLogger.LogTestResult(
            "RangeRepository_DeleteAsync_ShouldDeleteRangeEntity",
            passed,
            "Range entity deletion",
            "Should delete the range entity",
            $"DeletedRange={deletedRange == null}"
        );
        
        Assert.Null(deletedRange);
    }

    [Fact]
    public async Task EventRepository_AddAsync_ShouldCreateEventEntity()
    {
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
        var passed = createdEvent.Id != Guid.Empty && createdEvent.RangeId == createdRange.Id;
        
        TestResultLogger.LogTestResult(
            "EventRepository_AddAsync_ShouldCreateEventEntity",
            passed,
            "Event entity creation",
            "Event should be created with valid ID and range reference",
            $"Id={createdEvent.Id}, RangeId={createdEvent.RangeId}"
        );
        
        Assert.NotEqual(Guid.Empty, createdEvent.Id);
        Assert.Equal(createdRange.Id, createdEvent.RangeId);
    }

    [Fact]
    public async Task TargetRepository_AddAsync_ShouldCreateTargetEntity()
    {
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
        var passed = createdTarget.Id != Guid.Empty && 
                    createdTarget.PosX == 100 && 
                    createdTarget.PosY == 200;
        
        TestResultLogger.LogTestResult(
            "TargetRepository_AddAsync_ShouldCreateTargetEntity",
            passed,
            "Target entity creation",
            "Target should be created with valid ID and position",
            $"Id={createdTarget.Id}, PosX={createdTarget.PosX}, PosY={createdTarget.PosY}"
        );
        
        Assert.NotEqual(Guid.Empty, createdTarget.Id);
        Assert.Equal(100, createdTarget.PosX);
        Assert.Equal(200, createdTarget.PosY);
    }

    [Fact]
    public async Task HitRepository_AddAsync_ShouldCreateHitEntity()
    {
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
        var passed = createdHit.Id != Guid.Empty && 
                    createdHit.TargetId == createdTarget.Id && 
                    createdHit.EventId == createdEvent.Id;
        
        TestResultLogger.LogTestResult(
            "HitRepository_AddAsync_ShouldCreateHitEntity",
            passed,
            "Hit entity creation",
            "Hit should be created with valid ID and references",
            $"Id={createdHit.Id}, TargetId={createdHit.TargetId}, EventId={createdHit.EventId}"
        );
        
        Assert.NotEqual(Guid.Empty, createdHit.Id);
        Assert.Equal(createdTarget.Id, createdHit.TargetId);
        Assert.Equal(createdEvent.Id, createdHit.EventId);
        Assert.Equal(150.5f, createdHit.RangeToTarget);
    }

    [Fact]
    public async Task RangeRepository_GetByIdAsync_ShouldReturnNullForNonExistentId()
    {
        // Arrange
        var nonExistentId = Guid.NewGuid();

        // Act
        var result = await _rangeRepository.GetByIdAsync(nonExistentId);

        // Assert
        var passed = result == null;
        
        TestResultLogger.LogTestResult(
            "RangeRepository_GetByIdAsync_ShouldReturnNullForNonExistentId",
            passed,
            "Range entity retrieval - non-existent ID",
            "Should return null for non-existent ID",
            $"Result={result == null}"
        );
        
        Assert.Null(result);
    }

    [Fact]
    public async Task RangeRepository_UpdateAsync_ShouldThrowForNonExistentEntity()
    {
        // Arrange
        var nonExistentRange = new RangeEntity
        {
            Id = Guid.NewGuid(),
            Start = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            End = DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(),
            Description = "Non-existent Range",
            Timestamp = DateTime.UtcNow
        };

        // Act & Assert
        var exception = await Assert.ThrowsAsync<DbUpdateConcurrencyException>(() => 
            _rangeRepository.UpdateAsync(nonExistentRange));
        
        TestResultLogger.LogTestResult(
            "RangeRepository_UpdateAsync_ShouldThrowForNonExistentEntity",
            exception != null,
            "Range entity update - non-existent entity",
            "Should throw DbUpdateConcurrencyException for non-existent entity",
            exception.Message
        );
        
        Assert.NotNull(exception);
    }

    [Fact]
    public async Task RangeRepository_DeleteAsync_ShouldNotThrowForNonExistentId()
    {
        // Arrange
        var nonExistentId = Guid.NewGuid();

        // Act & Assert
        var exception = await Record.ExceptionAsync(() => 
            _rangeRepository.DeleteAsync(nonExistentId));
        
        var passed = exception == null;
        
        TestResultLogger.LogTestResult(
            "RangeRepository_DeleteAsync_ShouldNotThrowForNonExistentId",
            passed,
            "Range entity deletion - non-existent ID",
            "Should not throw for non-existent ID",
            exception?.Message ?? "No exception"
        );
        
        Assert.Null(exception);
    }

    public void Dispose()
    {
        _dbContext?.Dispose();
        _serviceProvider?.Dispose();
    }
}
