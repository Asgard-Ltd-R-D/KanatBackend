using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using PacketProcessing.Config;
using PacketProcessing.Context;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories;
using PacketProcessing.Tests;
using PacketProcessing.Utils.Enums;
using QuestDB;
using QuestDB.Senders;
using Xunit;

namespace PacketProcessing.Tests.unit.RepositoryTests;

/// <summary>
/// Tests for PacketRepository operations (QuestDB only)
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
    private readonly string _questDbConnectionString;
    private readonly string _ilpHttpConnection;

    public PacketRepositoryTests()
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
                {"ConnectionStrings:QuestDb", "Host=localhost;Port=9009;Database=qdb;Username=quest;Password=quest;"},
                {"Postgres:Host", "localhost"},
                {"Postgres:Port", "56432"},
                {"Postgres:Database", "pdb"},
                {"Postgres:Username", "postgres"},
                {"Postgres:Password", "postgres"},
                {"QuestDb:Host", "localhost"},
                {"QuestDb:PostgresPort", "8812"},
                {"QuestDb:Database", "qdb"},
                {"QuestDb:Username", "quest"},
                {"QuestDb:Password", "quest"},
                {"QuestDb:IlpHttpPort", "9000"}
            })
            .Build();

        // Configure database services
        DatabaseConfiguration.ConfigureServices(services, configuration);
        
        var serviceProvider = services.BuildServiceProvider();
        
        // Get repositories from DI container
        _motionRepository = serviceProvider.GetRequiredService<IPacketRepository<MotionPacketEntity>>();
        _onvifRepository = serviceProvider.GetRequiredService<IPacketRepository<OnVIFPacketEntity>>();
        _safetyRepository = serviceProvider.GetRequiredService<IPacketRepository<SafetyPacketEntity>>();
        
        // Get context and loggers
        _context = serviceProvider.GetRequiredService<AppDbContext>();
        _motionLogger = serviceProvider.GetRequiredService<ILogger<PacketRepository<MotionPacketEntity>>>();
        _onvifLogger = serviceProvider.GetRequiredService<ILogger<PacketRepository<OnVIFPacketEntity>>>();
        _safetyLogger = serviceProvider.GetRequiredService<ILogger<PacketRepository<SafetyPacketEntity>>>();
        _contextLogger = serviceProvider.GetRequiredService<ILogger<AppDbContext>>();
        _questDbConnectionString = configuration.GetConnectionString("QuestDb")!;
        
        // Build ILP HTTP connection string for Sender.New (http::addr=host:port;username=...;password=...;)
        var questHost = configuration["QuestDb:Host"] ?? "localhost";
        var questIlpHttpPort = configuration["QuestDb:IlpHttpPort"] ?? "9009";
        var questUser = configuration["QuestDb:Username"] ?? "quest";
        var questPass = configuration["QuestDb:Password"] ?? "quest";
        _ilpHttpConnection = $"http::addr={questHost}:{questIlpHttpPort};username={questUser};password={questPass};";
        
        // Ensure database is created
        _context.Database.EnsureCreated();
    }

    [Fact]
    public async Task WriteQuestDbAsync_ShouldThrowArgumentNullException_WhenCalledWithNullSender()
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
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(async () => 
            await _motionRepository.WriteQuestDbAsync(null!, entity));

        _motionLogger.LogInformation("Actual: ArgumentNullException thrown with message: {Message}", 
            exception.Message);
        _motionLogger.LogInformation("Result: PASS");
    }

    [Fact]
    public async Task WriteQuestDbAsync_ShouldWriteEntityWithValidSender()
    {
        // Arrange
        var entity = new MotionPacketEntity
        {
            Type = true,
            OpCode = "VALID_TEST",
            OpCodeDescription = "Valid Test",
            Axis = 25,
            FloatValue = 250.0f,
            Timestamp = DateTime.UtcNow
        };
        
        using var sender = Sender.New(_ilpHttpConnection);

        _motionLogger.LogInformation("=== WriteQuestDbAsync (Valid Sender) Test ===");
        _motionLogger.LogInformation("Input: Entity with OpCode={OpCode}, valid sender", entity.OpCode);
        _motionLogger.LogInformation("Expected: Entity should be written successfully");

        // Act
        await _motionRepository.WriteQuestDbAsync(sender, entity);

        // Assert
        _motionLogger.LogInformation("Actual: Entity written successfully");
        _motionLogger.LogInformation("Result: PASS");
    }

    [Fact]
    public async Task WriteBatchQuestDbAsync_ShouldHandleEmptyBatch()
    {
        // Arrange
        var emptyBatch = new List<MotionPacketEntity>();
        using var sender = Sender.New(_ilpHttpConnection);

        _motionLogger.LogInformation("=== WriteBatchQuestDbAsync (Empty Batch) Test ===");
        _motionLogger.LogInformation("Input: Empty batch with {Count} entities, valid sender", emptyBatch.Count);
        _motionLogger.LogInformation("Expected: Should handle empty batch gracefully");

        // Act
        await _motionRepository.WriteBatchQuestDbAsync(sender, emptyBatch);

        // Assert
        _motionLogger.LogInformation("Actual: Empty batch handled gracefully");
        _motionLogger.LogInformation("Result: PASS");
    }

    [Fact]
    public async Task WriteBatchQuestDbAsync_ShouldThrowArgumentNullException_WhenCalledWithNullSender()
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
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(async () => 
            await _motionRepository.WriteBatchQuestDbAsync(null!, entities));

        _motionLogger.LogInformation("Actual: ArgumentNullException thrown with message: {Message}", 
            exception.Message);
        _motionLogger.LogInformation("Result: PASS");
    }

    [Fact]
    public async Task WriteBatchQuestDbAsync_ShouldWriteBatchWithValidSender()
    {
        // Arrange
        var entities = new List<MotionPacketEntity>
        {
            new() { Type = true, OpCode = "BATCH1", OpCodeDescription = "Batch Test 1", Axis = 1, FloatValue = 1.0f, Timestamp = DateTime.UtcNow },
            new() { Type = false, OpCode = "BATCH2", OpCodeDescription = "Batch Test 2", Axis = 2, FloatValue = 2.0f, Timestamp = DateTime.UtcNow }
        };
        
        using var sender = Sender.New(_ilpHttpConnection);

        _motionLogger.LogInformation("=== WriteBatchQuestDbAsync (Valid Sender) Test ===");
        _motionLogger.LogInformation("Input: {Count} entities, valid sender", entities.Count);
        _motionLogger.LogInformation("Expected: Batch should be written successfully");

        // Act
        await _motionRepository.WriteBatchQuestDbAsync(sender, entities);

        // Assert
        _motionLogger.LogInformation("Actual: Batch written successfully");
        _motionLogger.LogInformation("Result: PASS");
    }

    [Fact]
    public async Task GetAllFromQuestDbAsync_ShouldNotThrow()
    {
        // Arrange
        _motionLogger.LogInformation("=== GetAllFromQuestDbAsync Test ===");
        _motionLogger.LogInformation("Input: No parameters");
        _motionLogger.LogInformation("Expected: Should not throw (may return empty collection)");

        // Act & Assert
        var exception = await Record.ExceptionAsync(async () => 
            await _motionRepository.GetAllFromQuestDbAsync());

        _motionLogger.LogInformation("Actual: Method completed without exception");
        _motionLogger.LogInformation("Result: {Result}", exception == null ? "PASS" : "FAIL");
        
        Assert.Null(exception);
    }

    [Fact]
    public async Task DeleteAllFromQuestDbAsync_ShouldNotThrow()
    {
        // Arrange
        _motionLogger.LogInformation("=== DeleteAllFromQuestDbAsync Test ===");
        _motionLogger.LogInformation("Input: No parameters");
        _motionLogger.LogInformation("Expected: Should not throw");

        // Act & Assert
        var exception = await Record.ExceptionAsync(async () => 
            await _motionRepository.DeleteAllFromQuestDbAsync());

        _motionLogger.LogInformation("Actual: Method completed without exception");
        _motionLogger.LogInformation("Result: {Result}", exception == null ? "PASS" : "FAIL");
        
        Assert.Null(exception);
    }

    [Fact]
    public async Task GetPaginatedFromQuestDbAsync_ShouldNotThrow()
    {
        // Arrange
        var startTime = DateTime.UtcNow.AddHours(-1);
        var endTime = DateTime.UtcNow.AddHours(1);
        var page = 1;
        var pageSize = 10;

        _motionLogger.LogInformation("=== GetPaginatedFromQuestDbAsync Test ===");
        _motionLogger.LogInformation("Input: StartTime={StartTime}, EndTime={EndTime}, Page={Page}, PageSize={PageSize}", 
            startTime, endTime, page, pageSize);
        _motionLogger.LogInformation("Expected: Should not throw (may return empty collection)");

        // Act & Assert
        var exception = await Record.ExceptionAsync(async () => 
            await _motionRepository.GetPaginatedFromQuestDbAsync(startTime, endTime, OrderBy.Asc, page, pageSize));

        _motionLogger.LogInformation("Actual: Method completed without exception");
        _motionLogger.LogInformation("Result: {Result}", exception == null ? "PASS" : "FAIL");
        
        Assert.Null(exception);
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
        
        using var sender = Sender.New(_ilpHttpConnection);

        _motionLogger.LogInformation("=== MotionPacketEntity Repository Test ===");
        _motionLogger.LogInformation("Input: MotionPacketEntity with OpCode={OpCode}, Axis={Axis}", 
            entity.OpCode, entity.Axis);
        _motionLogger.LogInformation("Expected: Entity should be written successfully");

        // Act & Assert
        await _motionRepository.WriteQuestDbAsync(sender, entity);
        _motionLogger.LogInformation("Step 1: Entity written successfully");

        var allEntities = await _motionRepository.GetAllFromQuestDbAsync();
        _motionLogger.LogInformation("Step 2: GetAllFromQuestDbAsync completed");

        await _motionRepository.DeleteAllFromQuestDbAsync();
        _motionLogger.LogInformation("Step 3: DeleteAllFromQuestDbAsync completed");

        _motionLogger.LogInformation("Result: PASS");
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
        
        using var sender = Sender.New(_ilpHttpConnection);

        _onvifLogger.LogInformation("=== OnVIFPacketEntity Repository Test ===");
        _onvifLogger.LogInformation("Input: OnVIFPacketEntity with Description={Description}, Measurement={Measurement}", 
            entity.Description, entity.Measurement);
        _onvifLogger.LogInformation("Expected: Entity should be written successfully");

        // Act & Assert
        await _onvifRepository.WriteQuestDbAsync(sender, entity);
        _onvifLogger.LogInformation("Step 1: Entity written successfully");

        var allEntities = await _onvifRepository.GetAllFromQuestDbAsync();
        _onvifLogger.LogInformation("Step 2: GetAllFromQuestDbAsync completed");

        await _onvifRepository.DeleteAllFromQuestDbAsync();
        _onvifLogger.LogInformation("Step 3: DeleteAllFromQuestDbAsync completed");

        _onvifLogger.LogInformation("Result: PASS");
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
        
        using var sender = Sender.New(_ilpHttpConnection);

        _safetyLogger.LogInformation("=== SafetyPacketEntity Repository Test ===");
        _safetyLogger.LogInformation("Input: SafetyPacketEntity with OpCode={OpCode}, State={State}", 
            entity.OpCode, entity.State);
        _safetyLogger.LogInformation("Expected: Entity should be written successfully");

        // Act & Assert
        await _safetyRepository.WriteQuestDbAsync(sender, entity);
        _safetyLogger.LogInformation("Step 1: Entity written successfully");

        var allEntities = await _safetyRepository.GetAllFromQuestDbAsync();
        _safetyLogger.LogInformation("Step 2: GetAllFromQuestDbAsync completed");

        await _safetyRepository.DeleteAllFromQuestDbAsync();
        _safetyLogger.LogInformation("Step 3: DeleteAllFromQuestDbAsync completed");

        _safetyLogger.LogInformation("Result: PASS");
    }

    public void Dispose()
    {
        _context?.Dispose();
    }
}
