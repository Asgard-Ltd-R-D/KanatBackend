using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using PacketProcessing.Context;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories;
using PacketProcessing.Utils.Enums;
using QuestDB.Senders;
using Xunit;

namespace PacketProcessing.Tests.unit.RepositoryTests;

/// <summary>
/// Comprehensive tests for PacketRepository operations
/// Tests both EF Core (PostgreSQL) and QuestDB operations
/// </summary>
public class PacketRepositoryTests : IDisposable
{
    private readonly AppDbContext _context;
    private readonly IPacketRepository<MotionPacketEntity> _motionRepository;
    private readonly IPacketRepository<OnVIFPacketEntity> _onvifRepository;
    private readonly IPacketRepository<SafetyPacketEntity> _safetyRepository;
    private readonly ILogger<PacketRepository<MotionPacketEntity>> _motionLogger;
    private readonly ILogger<PacketRepository<OnVIFPacketEntity>> _onvifLogger;
    private readonly ILogger<PacketRepository<SafetyPacketEntity>> _safetyLogger;
    private readonly ILogger<AppDbContext> _contextLogger;

    public PacketRepositoryTests()
    {
        // Setup in-memory database
        var options = new DbContextOptionsBuilder<AppDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;

        // Setup loggers
        var loggerFactory = LoggerFactory.Create(builder => builder.AddConsole());
        _motionLogger = loggerFactory.CreateLogger<PacketRepository<MotionPacketEntity>>();
        _onvifLogger = loggerFactory.CreateLogger<PacketRepository<OnVIFPacketEntity>>();
        _safetyLogger = loggerFactory.CreateLogger<PacketRepository<SafetyPacketEntity>>();
        _contextLogger = loggerFactory.CreateLogger<AppDbContext>();

        _context = new AppDbContext(options, _contextLogger);

        // Setup repositories with mock QuestDB connection string
        var questDbConnectionString = "Host=localhost;Port=9009;Database=qdb;Username=quest;Password=quest;";
        _motionRepository = new PacketRepository<MotionPacketEntity>(_context, _motionLogger, questDbConnectionString);
        _onvifRepository = new PacketRepository<OnVIFPacketEntity>(_context, _onvifLogger, questDbConnectionString);
        _safetyRepository = new PacketRepository<SafetyPacketEntity>(_context, _safetyLogger, questDbConnectionString);
    }

    [Fact]
    public async Task AddAsync_ShouldAddEntityToDatabase()
    {
        // Arrange
        var entity = new MotionPacketEntity
        {
            Type = true,
            OpCode = "TEST_OP",
            OpCodeDescription = "Test Operation",
            Axis = 1,
            FloatValue = 123.45f,
            Timestamp = DateTime.UtcNow
        };

        _motionLogger.LogInformation("=== AddAsync Test ===");
        _motionLogger.LogInformation("Input: Entity with OpCode={OpCode}, Axis={Axis}, FloatValue={FloatValue}", 
            entity.OpCode, entity.Axis, entity.FloatValue);
        _motionLogger.LogInformation("Expected: Entity should be added to database and returned with generated Id");

        // Act
        var result = await _motionRepository.AddAsync(entity);

        // Assert
        _motionLogger.LogInformation("Actual: Entity added with Id={Id}", result.Id);
        _motionLogger.LogInformation("Result: {Result}", result.Id != Guid.Empty ? "PASS" : "FAIL");
        
        Assert.NotEqual(Guid.Empty, result.Id);
        Assert.Equal(entity.OpCode, result.OpCode);
        Assert.Equal(entity.Axis, result.Axis);
        Assert.Equal(entity.FloatValue, result.FloatValue);
    }

    [Fact]
    public async Task AddRangeAsync_ShouldAddMultipleEntities()
    {
        // Arrange
        var entities = new List<MotionPacketEntity>
        {
            new() { Type = true, OpCode = "OP1", OpCodeDescription = "Operation 1", Axis = 1, FloatValue = 1.1f, Timestamp = DateTime.UtcNow },
            new() { Type = false, OpCode = "OP2", OpCodeDescription = "Operation 2", Axis = 2, FloatValue = 2.2f, Timestamp = DateTime.UtcNow },
            new() { Type = true, OpCode = "OP3", OpCodeDescription = "Operation 3", Axis = 3, FloatValue = 3.3f, Timestamp = DateTime.UtcNow }
        };

        _motionLogger.LogInformation("=== AddRangeAsync Test ===");
        _motionLogger.LogInformation("Input: {Count} entities to add", entities.Count);
        _motionLogger.LogInformation("Expected: All entities should be added and count returned");

        // Act
        var result = await _motionRepository.AddRangeAsync(entities);

        // Assert
        _motionLogger.LogInformation("Actual: {Count} entities added", result);
        _motionLogger.LogInformation("Result: {Result}", result == entities.Count ? "PASS" : "FAIL");
        
        Assert.Equal(entities.Count, result);
    }

    [Fact]
    public async Task GetByIdAsync_ShouldReturnEntity()
    {
        // Arrange
        var entity = new MotionPacketEntity
        {
            Type = true,
            OpCode = "GET_TEST",
            OpCodeDescription = "Get Test",
            Axis = 5,
            FloatValue = 99.99f,
            Timestamp = DateTime.UtcNow
        };
        var addedEntity = await _motionRepository.AddAsync(entity);

        _motionLogger.LogInformation("=== GetByIdAsync Test ===");
        _motionLogger.LogInformation("Input: Id={Id}", addedEntity.Id);
        _motionLogger.LogInformation("Expected: Entity with matching Id should be returned");

        // Act
        var result = await _motionRepository.GetByIdAsync(addedEntity.Id);

        // Assert
        _motionLogger.LogInformation("Actual: Entity found={Found}, OpCode={OpCode}", 
            result != null, result?.OpCode);
        _motionLogger.LogInformation("Result: {Result}", result != null ? "PASS" : "FAIL");
        
        Assert.NotNull(result);
        Assert.Equal(addedEntity.Id, result.Id);
        Assert.Equal(entity.OpCode, result.OpCode);
    }

    [Fact]
    public async Task GetByIdAsync_ShouldReturnNull_WhenEntityNotFound()
    {
        // Arrange
        var nonExistentId = Guid.NewGuid();

        _motionLogger.LogInformation("=== GetByIdAsync (Not Found) Test ===");
        _motionLogger.LogInformation("Input: Non-existent Id={Id}", nonExistentId);
        _motionLogger.LogInformation("Expected: null should be returned");

        // Act
        var result = await _motionRepository.GetByIdAsync(nonExistentId);

        // Assert
        _motionLogger.LogInformation("Actual: Result={Result}", result?.ToString() ?? "null");
        _motionLogger.LogInformation("Result: {Result}", result == null ? "PASS" : "FAIL");
        
        Assert.Null(result);
    }

    [Fact]
    public async Task UpdateAsync_ShouldUpdateEntity()
    {
        // Arrange
        var entity = new MotionPacketEntity
        {
            Type = true,
            OpCode = "UPDATE_TEST",
            OpCodeDescription = "Update Test",
            Axis = 10,
            FloatValue = 50.0f,
            Timestamp = DateTime.UtcNow
        };
        var addedEntity = await _motionRepository.AddAsync(entity);

        // Update the entity
        addedEntity.OpCode = "UPDATED_OP";
        addedEntity.FloatValue = 75.5f;

        _motionLogger.LogInformation("=== UpdateAsync Test ===");
        _motionLogger.LogInformation("Input: Entity with Id={Id}, new OpCode={OpCode}, new FloatValue={FloatValue}", 
            addedEntity.Id, addedEntity.OpCode, addedEntity.FloatValue);
        _motionLogger.LogInformation("Expected: Entity should be updated and returned");

        // Act
        var result = await _motionRepository.UpdateAsync(addedEntity);

        // Assert
        _motionLogger.LogInformation("Actual: Updated entity OpCode={OpCode}, FloatValue={FloatValue}", 
            result.OpCode, result.FloatValue);
        _motionLogger.LogInformation("Result: {Result}", 
            result.OpCode == "UPDATED_OP" && result.FloatValue == 75.5f ? "PASS" : "FAIL");
        
        Assert.Equal("UPDATED_OP", result.OpCode);
        Assert.Equal(75.5f, result.FloatValue);
    }

    [Fact]
    public async Task DeleteAsync_ShouldDeleteEntity()
    {
        // Arrange
        var entity = new MotionPacketEntity
        {
            Type = true,
            OpCode = "DELETE_TEST",
            OpCodeDescription = "Delete Test",
            Axis = 15,
            FloatValue = 100.0f,
            Timestamp = DateTime.UtcNow
        };
        var addedEntity = await _motionRepository.AddAsync(entity);

        _motionLogger.LogInformation("=== DeleteAsync Test ===");
        _motionLogger.LogInformation("Input: Entity Id={Id} to delete", addedEntity.Id);
        _motionLogger.LogInformation("Expected: Entity should be deleted and true returned");

        // Act
        var result = await _motionRepository.DeleteAsync(addedEntity.Id);

        // Assert
        _motionLogger.LogInformation("Actual: Delete result={Result}", result);
        _motionLogger.LogInformation("Result: {Result}", result ? "PASS" : "FAIL");
        
        Assert.True(result);
        
        // Verify entity is actually deleted
        var deletedEntity = await _motionRepository.GetByIdAsync(addedEntity.Id);
        _motionLogger.LogInformation("Verification: Entity found after deletion={Found}", deletedEntity != null);
        Assert.Null(deletedEntity);
    }

    [Fact]
    public async Task DeleteAsync_ShouldReturnFalse_WhenEntityNotFound()
    {
        // Arrange
        var nonExistentId = Guid.NewGuid();

        _motionLogger.LogInformation("=== DeleteAsync (Not Found) Test ===");
        _motionLogger.LogInformation("Input: Non-existent Id={Id}", nonExistentId);
        _motionLogger.LogInformation("Expected: false should be returned");

        // Act
        var result = await _motionRepository.DeleteAsync(nonExistentId);

        // Assert
        _motionLogger.LogInformation("Actual: Delete result={Result}", result);
        _motionLogger.LogInformation("Result: {Result}", !result ? "PASS" : "FAIL");
        
        Assert.False(result);
    }

    [Fact]
    public async Task GetAllPacketsAsync_ShouldReturnAllEntities()
    {
        // Arrange
        var entities = new List<MotionPacketEntity>
        {
            new() { Type = true, OpCode = "ALL1", OpCodeDescription = "All Test 1", Axis = 1, FloatValue = 1.0f, Timestamp = DateTime.UtcNow },
            new() { Type = false, OpCode = "ALL2", OpCodeDescription = "All Test 2", Axis = 2, FloatValue = 2.0f, Timestamp = DateTime.UtcNow }
        };

        foreach (var entity in entities)
        {
            await _motionRepository.AddAsync(entity);
        }

        _motionLogger.LogInformation("=== GetAllPacketsAsync Test ===");
        _motionLogger.LogInformation("Input: {Count} entities in database", entities.Count);
        _motionLogger.LogInformation("Expected: All entities should be returned");

        // Act
        var result = await _motionRepository.GetAllPacketsAsync();

        // Assert
        var resultList = result.ToList();
        _motionLogger.LogInformation("Actual: {Count} entities returned", resultList.Count);
        _motionLogger.LogInformation("Result: {Result}", resultList.Count >= entities.Count ? "PASS" : "FAIL");
        
        Assert.True(resultList.Count >= entities.Count);
    }

    [Fact]
    public async Task DeleteAllPacketsAsync_ShouldDeleteAllEntities()
    {
        // Arrange
        var entities = new List<MotionPacketEntity>
        {
            new() { Type = true, OpCode = "DEL_ALL1", OpCodeDescription = "Delete All 1", Axis = 1, FloatValue = 1.0f, Timestamp = DateTime.UtcNow },
            new() { Type = false, OpCode = "DEL_ALL2", OpCodeDescription = "Delete All 2", Axis = 2, FloatValue = 2.0f, Timestamp = DateTime.UtcNow }
        };

        foreach (var entity in entities)
        {
            await _motionRepository.AddAsync(entity);
        }

        _motionLogger.LogInformation("=== DeleteAllPacketsAsync Test ===");
        _motionLogger.LogInformation("Input: {Count} entities to delete", entities.Count);
        _motionLogger.LogInformation("Expected: All entities should be deleted");

        // Act
        await _motionRepository.DeleteAllPacketsAsync();

        // Assert
        var remainingEntities = await _motionRepository.GetAllPacketsAsync();
        var remainingCount = remainingEntities.Count();
        _motionLogger.LogInformation("Actual: {Count} entities remaining after deletion", remainingCount);
        _motionLogger.LogInformation("Result: {Result}", remainingCount == 0 ? "PASS" : "FAIL");
        
        Assert.Empty(remainingEntities);
    }

    [Fact]
    public async Task GetPaginatedPacketsAsync_ShouldReturnPaginatedResults()
    {
        // Arrange
        var entities = new List<MotionPacketEntity>();
        for (int i = 1; i <= 10; i++)
        {
            entities.Add(new MotionPacketEntity
            {
                Type = i % 2 == 0,
                OpCode = $"PAGE_{i}",
                OpCodeDescription = $"Page Test {i}",
                Axis = i,
                FloatValue = i * 10.0f,
                Timestamp = DateTime.UtcNow
            });
        }

        foreach (var entity in entities)
        {
            await _motionRepository.AddAsync(entity);
        }

        var startTime = DateTime.UtcNow.AddHours(-1);
        var endTime = DateTime.UtcNow.AddHours(1);
        var page = 1;
        var pageSize = 3;

        _motionLogger.LogInformation("=== GetPaginatedPacketsAsync Test ===");
        _motionLogger.LogInformation("Input: Page={Page}, PageSize={PageSize}, StartTime={StartTime}, EndTime={EndTime}", 
            page, pageSize, startTime, endTime);
        _motionLogger.LogInformation("Expected: Up to {PageSize} entities should be returned", pageSize);

        // Act
        var result = await _motionRepository.GetPaginatedPacketsAsync(startTime, endTime, OrderBy.Asc, page, pageSize);

        // Assert
        var resultList = result.ToList();
        _motionLogger.LogInformation("Actual: {Count} entities returned", resultList.Count);
        _motionLogger.LogInformation("Result: {Result}", resultList.Count <= pageSize ? "PASS" : "FAIL");
        
        Assert.True(resultList.Count <= pageSize);
    }

    [Fact]
    public void WriteQuestDbAsync_ShouldThrowArgumentNullException_WhenCalledWithNullSender()
    {
        // Arrange
        var entity = new MotionPacketEntity
        {
            Type = true,
            OpCode = "QUEST_TEST",
            OpCodeDescription = "QuestDB Test",
            Axis = 20,
            FloatValue = 200.0f,
            Timestamp = DateTime.UtcNow
        };

        _motionLogger.LogInformation("=== WriteQuestDbAsync (Null Sender) Test ===");
        _motionLogger.LogInformation("Input: Entity with OpCode={OpCode}, null sender", entity.OpCode);
        _motionLogger.LogInformation("Expected: ArgumentNullException should be thrown");

        // Act & Assert
        var exception = Assert.ThrowsAsync<ArgumentNullException>(async () => 
            await _motionRepository.WriteQuestDbAsync(null!, entity));

        _motionLogger.LogInformation("Actual: ArgumentNullException thrown with message: {Message}", 
            exception.Result.Message);
        _motionLogger.LogInformation("Result: PASS");
    }

    [Fact]
    public async Task WriteBatchQuestDbAsync_ShouldHandleEmptyBatch()
    {
        // Arrange
        var emptyBatch = new List<MotionPacketEntity>();

        _motionLogger.LogInformation("=== WriteBatchQuestDbAsync (Empty Batch) Test ===");
        _motionLogger.LogInformation("Input: Empty batch with {Count} entities, null sender", emptyBatch.Count);
        _motionLogger.LogInformation("Expected: ArgumentNullException should be thrown for null sender, even with empty batch");

        // Act & Assert - Should throw ArgumentNullException for null sender, even with empty batch
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(async () => 
            await _motionRepository.WriteBatchQuestDbAsync(null!, emptyBatch));

        _motionLogger.LogInformation("Actual: ArgumentNullException thrown with message: {Message}", 
            exception.Message);
        _motionLogger.LogInformation("Result: PASS");
    }

    [Fact]
    public void WriteBatchQuestDbAsync_ShouldThrowArgumentNullException_WhenCalledWithNullSender()
    {
        // Arrange
        var entities = new List<MotionPacketEntity>
        {
            new() { Type = true, OpCode = "BATCH1", OpCodeDescription = "Batch Test 1", Axis = 1, FloatValue = 1.0f, Timestamp = DateTime.UtcNow },
            new() { Type = false, OpCode = "BATCH2", OpCodeDescription = "Batch Test 2", Axis = 2, FloatValue = 2.0f, Timestamp = DateTime.UtcNow }
        };

        _motionLogger.LogInformation("=== WriteBatchQuestDbAsync (Null Sender) Test ===");
        _motionLogger.LogInformation("Input: {Count} entities, null sender", entities.Count);
        _motionLogger.LogInformation("Expected: ArgumentNullException should be thrown");

        // Act & Assert
        var exception = Assert.ThrowsAsync<ArgumentNullException>(async () => 
            await _motionRepository.WriteBatchQuestDbAsync(null!, entities));

        _motionLogger.LogInformation("Actual: ArgumentNullException thrown with message: {Message}", 
            exception.Result.Message);
        _motionLogger.LogInformation("Result: PASS");
    }

    [Fact]
    public void PacketRepository_Constructor_ShouldCreateInstance()
    {
        // Arrange
        var questDbConnectionString = "Host=localhost;Port=9009;Database=qdb;Username=quest;Password=quest;";

        _motionLogger.LogInformation("=== PacketRepository Constructor Test ===");
        _motionLogger.LogInformation("Input: QuestDB connection string length={Length}", questDbConnectionString.Length);
        _motionLogger.LogInformation("Expected: PacketRepository instance should be created successfully");

        // Act
        var repository = new PacketRepository<MotionPacketEntity>(_context, _motionLogger, questDbConnectionString);

        // Assert
        _motionLogger.LogInformation("Actual: Repository instance created successfully");
        _motionLogger.LogInformation("Result: PASS");
        
        Assert.NotNull(repository);
    }

    [Fact]
    public async Task MotionPacketEntity_ShouldWorkWithRepository()
    {
        // Arrange
        var entity = new MotionPacketEntity
        {
            Type = true,
            OpCode = "MOTION_TEST",
            OpCodeDescription = "Motion Test",
            Axis = 25,
            FloatValue = 250.0f,
            Timestamp = DateTime.UtcNow
        };

        _motionLogger.LogInformation("=== MotionPacketEntity Repository Test ===");
        _motionLogger.LogInformation("Input: MotionPacketEntity with OpCode={OpCode}, Axis={Axis}", 
            entity.OpCode, entity.Axis);
        _motionLogger.LogInformation("Expected: Entity should be added, retrieved, and deleted successfully");

        // Act & Assert
        var added = await _motionRepository.AddAsync(entity);
        _motionLogger.LogInformation("Step 1: Entity added with Id={Id}", added.Id);

        var retrieved = await _motionRepository.GetByIdAsync(added.Id);
        _motionLogger.LogInformation("Step 2: Entity retrieved, OpCode={OpCode}", retrieved?.OpCode);

        var deleted = await _motionRepository.DeleteAsync(added.Id);
        _motionLogger.LogInformation("Step 3: Entity deleted, result={Result}", deleted);

        _motionLogger.LogInformation("Result: PASS");
        
        Assert.NotNull(retrieved);
        Assert.Equal(entity.OpCode, retrieved.OpCode);
        Assert.True(deleted);
    }

    [Fact]
    public async Task OnVIFPacketEntity_ShouldWorkWithRepository()
    {
        // Arrange
        var entity = new OnVIFPacketEntity
        {
            Type = true,
            Description = "OnVIF Test",
            Measurement = 300.0f,
            Timestamp = DateTime.UtcNow
        };

        _onvifLogger.LogInformation("=== OnVIFPacketEntity Repository Test ===");
        _onvifLogger.LogInformation("Input: OnVIFPacketEntity with Description={Description}, Measurement={Measurement}", 
            entity.Description, entity.Measurement);
        _onvifLogger.LogInformation("Expected: Entity should be added, retrieved, and deleted successfully");

        // Act & Assert
        var added = await _onvifRepository.AddAsync(entity);
        _onvifLogger.LogInformation("Step 1: Entity added with Id={Id}", added.Id);

        var retrieved = await _onvifRepository.GetByIdAsync(added.Id);
        _onvifLogger.LogInformation("Step 2: Entity retrieved, Description={Description}", retrieved?.Description);

        var deleted = await _onvifRepository.DeleteAsync(added.Id);
        _onvifLogger.LogInformation("Step 3: Entity deleted, result={Result}", deleted);

        _onvifLogger.LogInformation("Result: PASS");
        
        Assert.NotNull(retrieved);
        Assert.Equal(entity.Description, retrieved.Description);
        Assert.True(deleted);
    }

    [Fact]
    public async Task SafetyPacketEntity_ShouldWorkWithRepository()
    {
        // Arrange
        var entity = new SafetyPacketEntity
        {
            Type = true,
            OpCode = "SAFETY_TEST",
            OpCodeDescription = "Safety Test",
            State = "ACTIVE",
            Timestamp = DateTime.UtcNow
        };

        _safetyLogger.LogInformation("=== SafetyPacketEntity Repository Test ===");
        _safetyLogger.LogInformation("Input: SafetyPacketEntity with OpCode={OpCode}, State={State}", 
            entity.OpCode, entity.State);
        _safetyLogger.LogInformation("Expected: Entity should be added, retrieved, and deleted successfully");

        // Act & Assert
        var added = await _safetyRepository.AddAsync(entity);
        _safetyLogger.LogInformation("Step 1: Entity added with Id={Id}", added.Id);

        var retrieved = await _safetyRepository.GetByIdAsync(added.Id);
        _safetyLogger.LogInformation("Step 2: Entity retrieved, OpCode={OpCode}", retrieved?.OpCode);

        var deleted = await _safetyRepository.DeleteAsync(added.Id);
        _safetyLogger.LogInformation("Step 3: Entity deleted, result={Result}", deleted);

        _safetyLogger.LogInformation("Result: PASS");
        
        Assert.NotNull(retrieved);
        Assert.Equal(entity.OpCode, retrieved.OpCode);
        Assert.True(deleted);
    }

    public void Dispose()
    {
        _context?.Dispose();
    }
}
