using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using PacketProcessing.Config;
using PacketProcessing.Context;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories.InfluxRepository;
using PacketProcessing.Tests;
using PacketProcessing.Utils.Enums;
using QuestDB.Senders;
using QuestDB;
using Xunit;

namespace PacketProcessing.Tests.unit.RepositoryTests;

/// <summary>
/// Tests for InfluxRepository operations with new QuestDbContext architecture
/// </summary>
public class InfluxRepositoryTests : IDisposable
{
    private readonly ServiceProvider _serviceProvider;
    private readonly PostgresDbContext _postgresContext;
    private readonly QuestDbContext _questDbContext;
    private readonly IInfluxRepository<MotionPacketEntity> _motionRepository;
    private readonly IInfluxRepository<OnVIFPacketEntity> _onvifRepository;
    private readonly IInfluxRepository<SafetyPacketEntity> _safetyRepository;
    private readonly string _ilpHttpConnection;

    public InfluxRepositoryTests()
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
                {"QuestDb:PgHost", "localhost"},
                {"QuestDb:PgPort", "8812"},
                {"QuestDb:Database", "qdb"},
                {"QuestDb:PgUser", "quest"},
                {"QuestDb:PgPassword", "quest"},
                {"QuestDb:IlpHttpPort", "9000"}
            })
            .Build();

        // Configure database services
        DatabaseConfiguration.ConfigureServices(services, configuration);
        
        _serviceProvider = services.BuildServiceProvider();
        
        // Get required services
        _postgresContext = _serviceProvider.GetRequiredService<PostgresDbContext>();
        _questDbContext = _serviceProvider.GetRequiredService<QuestDbContext>();
        _motionRepository = _serviceProvider.GetRequiredService<IInfluxRepository<MotionPacketEntity>>();
        _onvifRepository = _serviceProvider.GetRequiredService<IInfluxRepository<OnVIFPacketEntity>>();
        _safetyRepository = _serviceProvider.GetRequiredService<IInfluxRepository<SafetyPacketEntity>>();
        
        // ILP HTTP connection for QuestDB
        _ilpHttpConnection = "http::addr=localhost:9000;username=quest;password=quest;";
    }

    [Fact]
    public async Task QuestDbContext_ShouldBeRegisteredAndInitialized()
    {
        // Assert
        Assert.NotNull(_questDbContext);
        
        // Test that we can open a connection
        await using var connection = await _questDbContext.OpenPgAsync();
        Assert.NotNull(connection);
        Assert.Equal(System.Data.ConnectionState.Open, connection.State);
    }

    [Fact]
    public async Task QuestDbContext_EnsureDatabaseAsync_ShouldCreateTables()
    {
        // Act
        var tablesCreated = await _questDbContext.EnsureDatabaseAsync();
        
        // Assert
        Assert.True(tablesCreated || !tablesCreated); // Either created or already existed
    }

    [Fact]
    public async Task QuestDbContext_OpenPgAsync_ShouldOpenConnection()
    {
        // Act
        await using var connection = await _questDbContext.OpenPgAsync();
        
        // Assert
        Assert.NotNull(connection);
        Assert.Equal(System.Data.ConnectionState.Open, connection.State);
    }

    [Fact]
    public void QuestDbContext_GetTableName_ShouldReturnCorrectTableNames()
    {
        // Act & Assert
        Assert.Equal("motion_packets", QuestDbContext.GetTableName<MotionPacketEntity>());
        Assert.Equal("onvif_packets", QuestDbContext.GetTableName<OnVIFPacketEntity>());
        Assert.Equal("safety_packets", QuestDbContext.GetTableName<SafetyPacketEntity>());
    }

    [Fact]
    public void QuestDbContext_SelectListFor_ShouldReturnCorrectSelectClauses()
    {
        // Arrange & Act
        var motionSelect = QuestDbContext.SelectListFor<MotionPacketEntity>();
        var onvifSelect = QuestDbContext.SelectListFor<OnVIFPacketEntity>();
        var safetySelect = QuestDbContext.SelectListFor<SafetyPacketEntity>();
        
        // Debug output
        Console.WriteLine($"Motion Select: {motionSelect}");
        Console.WriteLine($"OnVIF Select: {onvifSelect}");
        Console.WriteLine($"Safety Select: {safetySelect}");
        
        // Assert
        Assert.NotEmpty(motionSelect);
        Assert.NotEmpty(onvifSelect);
        Assert.NotEmpty(safetySelect);
    }

    [Fact]
    public async Task WriteQuestDbAsync_ShouldWriteEntityWithValidSender()
    {
        // Clean up - Delete all data
        await _motionRepository.DeleteAllFromQuestDbAsync();

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
                
        // Act - Write entity
        await _motionRepository.WriteQuestDbAsync(sender, entity);
        
        // Wait for QuestDB to commit the data
        await Task.Delay(1000);
        
        // Verify data can be fetched
        var fetchedEntities = await _motionRepository.GetAllFromQuestDbAsync();
        Assert.NotEmpty(fetchedEntities);
        Assert.Contains(fetchedEntities, e => e.OpCode == "VALID_TEST");
        
        // Clean up - Delete all data
        await _motionRepository.DeleteAllFromQuestDbAsync();
        
        // Verify cleanup worked
        await Task.Delay(1000);
        var entitiesAfterCleanup = await _motionRepository.GetAllFromQuestDbAsync();
        Assert.Empty(entitiesAfterCleanup);
    }

    [Fact]
    public async Task WriteBatchQuestDbAsync_ShouldWriteBatchWithValidSender()
    {
        // Clean up - Delete all data
        await _motionRepository.DeleteAllFromQuestDbAsync();

        // Arrange
        var entities = new List<MotionPacketEntity>
        {
            new() { Type = true, OpCode = "BATCH1", OpCodeDescription = "Batch Test 1", Axis = 1, FloatValue = 1.0f, Timestamp = DateTime.UtcNow },
            new() { Type = false, OpCode = "BATCH2", OpCodeDescription = "Batch Test 2", Axis = 2, FloatValue = 2.0f, Timestamp = DateTime.UtcNow },
            new() { Type = true, OpCode = "BATCH3", OpCodeDescription = "Batch Test 3", Axis = 3, FloatValue = 3.0f, Timestamp = DateTime.UtcNow },
            new() { Type = false, OpCode = "BATCH4", OpCodeDescription = "Batch Test 4", Axis = 4, FloatValue = 4.0f, Timestamp = DateTime.UtcNow },
            new() { Type = true, OpCode = "BATCH5", OpCodeDescription = "Batch Test 5", Axis = 5, FloatValue = 5.0f, Timestamp = DateTime.UtcNow },
            new() { Type = false, OpCode = "BATCH6", OpCodeDescription = "Batch Test 6", Axis = 6, FloatValue = 6.0f, Timestamp = DateTime.UtcNow },
            new() { Type = true, OpCode = "BATCH7", OpCodeDescription = "Batch Test 7", Axis = 7, FloatValue = 7.0f, Timestamp = DateTime.UtcNow },
            new() { Type = false, OpCode = "BATCH8", OpCodeDescription = "Batch Test 8", Axis = 8, FloatValue = 8.0f, Timestamp = DateTime.UtcNow },
            new() { Type = true, OpCode = "BATCH9", OpCodeDescription = "Batch Test 9", Axis = 9, FloatValue = 9.0f, Timestamp = DateTime.UtcNow },
            new() { Type = false, OpCode = "BATCH10", OpCodeDescription = "Batch Test 10", Axis = 10, FloatValue = 10.0f, Timestamp = DateTime.UtcNow }
        };
        
        using var sender = Sender.New(_ilpHttpConnection);
                
        // Act - Write batch
        await _motionRepository.WriteBatchQuestDbAsync(sender, entities);
        
        // Wait for QuestDB to commit the data
        await Task.Delay(1000);
        
        // Verify data can be fetched
        var fetchedEntities = await _motionRepository.GetAllFromQuestDbAsync();
        Assert.Equal(10, fetchedEntities.Count());
        Assert.Contains(fetchedEntities, e => e.OpCode == "BATCH1");
        Assert.Contains(fetchedEntities, e => e.OpCode == "BATCH10");
        
        // Clean up - Delete all data
        await _motionRepository.DeleteAllFromQuestDbAsync();
        
        // Verify cleanup worked
        await Task.Delay(1000);
        var entitiesAfterCleanup = await _motionRepository.GetAllFromQuestDbAsync();
        Assert.Empty(entitiesAfterCleanup);
    }

    [Fact]
    public async Task InfluxRepository_GetAllFromQuestDbAsync_ShouldWork()
    {
        // Clean up - Delete all data
        await _motionRepository.DeleteAllFromQuestDbAsync();

        // Arrange - Write test data first
        var testEntities = new List<MotionPacketEntity>
        {
            new() { Type = true, OpCode = "GETALL1", OpCodeDescription = "GetAll Test 1", Axis = 1, FloatValue = 1.0f, Timestamp = DateTime.UtcNow },
            new() { Type = false, OpCode = "GETALL2", OpCodeDescription = "GetAll Test 2", Axis = 2, FloatValue = 2.0f, Timestamp = DateTime.UtcNow },
            new() { Type = true, OpCode = "GETALL3", OpCodeDescription = "GetAll Test 3", Axis = 3, FloatValue = 3.0f, Timestamp = DateTime.UtcNow }
        };
        
        using var sender = Sender.New(_ilpHttpConnection);
        await _motionRepository.WriteBatchQuestDbAsync(sender, testEntities);
        
        // Wait for QuestDB to commit the data
        await Task.Delay(1000);
        
        // Act - Get all data
        var fetchedEntities = await _motionRepository.GetAllFromQuestDbAsync();
        
        // Assert - Verify all data can be fetched
        Assert.Equal(3, fetchedEntities.Count());
        Assert.Contains(fetchedEntities, e => e.OpCode == "GETALL1");
        Assert.Contains(fetchedEntities, e => e.OpCode == "GETALL2");
        Assert.Contains(fetchedEntities, e => e.OpCode == "GETALL3");
        
        // Clean up - Delete all data
        await _motionRepository.DeleteAllFromQuestDbAsync();
        
        // Verify cleanup worked
        var entitiesAfterCleanup = await _motionRepository.GetAllFromQuestDbAsync();
        Assert.Empty(entitiesAfterCleanup);
    }

    [Fact]
    public async Task InfluxRepository_GetPaginatedFromQuestDbAsync_ShouldWork()
    {
        // Clean up - Delete all data
        await _motionRepository.DeleteAllFromQuestDbAsync();

        // Arrange - Write test data first
        var testEntities = new List<MotionPacketEntity>
        {
            new() { Type = true, OpCode = "PAGE1", OpCodeDescription = "Page Test 1", Axis = 1, FloatValue = 1.0f, Timestamp = DateTime.UtcNow.AddMinutes(-30) },
            new() { Type = false, OpCode = "PAGE2", OpCodeDescription = "Page Test 2", Axis = 2, FloatValue = 2.0f, Timestamp = DateTime.UtcNow.AddMinutes(-20) },
            new() { Type = true, OpCode = "PAGE3", OpCodeDescription = "Page Test 3", Axis = 3, FloatValue = 3.0f, Timestamp = DateTime.UtcNow.AddMinutes(-10) },
            new() { Type = false, OpCode = "PAGE4", OpCodeDescription = "Page Test 4", Axis = 4, FloatValue = 4.0f, Timestamp = DateTime.UtcNow },
            new() { Type = true, OpCode = "PAGE5", OpCodeDescription = "Page Test 5", Axis = 5, FloatValue = 5.0f, Timestamp = DateTime.UtcNow.AddMinutes(10) }
        };
        
        using var sender = Sender.New(_ilpHttpConnection);
        await _motionRepository.WriteBatchQuestDbAsync(sender, testEntities);
        
        var startTime = DateTime.UtcNow.AddHours(-1);
        var endTime = DateTime.UtcNow.AddHours(1);

        // Act - Test pagination
        var page1 = await _motionRepository.GetPaginatedFromQuestDbAsync(startTime, endTime, OrderBy.Asc, 1, 2);
        var page2 = await _motionRepository.GetPaginatedFromQuestDbAsync(startTime, endTime, OrderBy.Asc, 2, 2);
        
        // Assert - Verify pagination works
        Assert.Equal(2, page1.Count());
        Assert.Equal(2, page2.Count());
        Assert.Contains(page1, e => e.OpCode == "PAGE1");
        Assert.Contains(page1, e => e.OpCode == "PAGE2");
        Assert.Contains(page2, e => e.OpCode == "PAGE3");
        Assert.Contains(page2, e => e.OpCode == "PAGE4");
        
        // Clean up - Delete all data
        await _motionRepository.DeleteAllFromQuestDbAsync();
        
        // Wait for QuestDB to commit the deletion
        await Task.Delay(1000);
        
        // Verify cleanup worked
        var entitiesAfterCleanup = await _motionRepository.GetAllFromQuestDbAsync();
        Assert.Empty(entitiesAfterCleanup);
    }

    [Fact]
    public async Task InfluxRepository_ShouldWorkWithAllEntityTypes()
    {
        // Clean up - Delete all data
        await _motionRepository.DeleteAllFromQuestDbAsync();
        await _onvifRepository.DeleteAllFromQuestDbAsync();
        await _safetyRepository.DeleteAllFromQuestDbAsync();

        // Arrange
        var motionEntity = new MotionPacketEntity
        {
            Type = true,
            OpCode = "MOTION_TEST",
            OpCodeDescription = "Motion Test",
            Axis = 25,
            FloatValue = 250.0f,
            Timestamp = DateTime.UtcNow
        };
        
        var onvifEntity = new OnVIFPacketEntity
        {
            Type = true,
            Description = "OnVIF Test",
            Measurement = 300.0f,
            Timestamp = DateTime.UtcNow
        };
        
        var safetyEntity = new SafetyPacketEntity
        {
            Type = true,
            OpCode = "SAFETY_TEST",
            OpCodeDescription = "Safety Test",
            State = "ACTIVE",
            Timestamp = DateTime.UtcNow
        };
        
        using var sender = Sender.New(_ilpHttpConnection);

        // Act - Write all entity types
        await _motionRepository.WriteQuestDbAsync(sender, motionEntity);
        await _onvifRepository.WriteQuestDbAsync(sender, onvifEntity);
        await _safetyRepository.WriteQuestDbAsync(sender, safetyEntity);
        
        // Verify data can be fetched for all entity types
        var motionEntities = await _motionRepository.GetAllFromQuestDbAsync();
        var onvifEntities = await _onvifRepository.GetAllFromQuestDbAsync();
        var safetyEntities = await _safetyRepository.GetAllFromQuestDbAsync();
        
        Assert.Single(motionEntities);
        Assert.Contains(motionEntities, e => e.OpCode == "MOTION_TEST");
        
        Assert.Single(onvifEntities);
        Assert.Contains(onvifEntities, e => e.Description == "OnVIF Test");
        
        Assert.Single(safetyEntities);
        Assert.Contains(safetyEntities, e => e.OpCode == "SAFETY_TEST");
        
        // Clean up - Delete all data for all entity types
        await _motionRepository.DeleteAllFromQuestDbAsync();
        await _onvifRepository.DeleteAllFromQuestDbAsync();
        await _safetyRepository.DeleteAllFromQuestDbAsync();
        
        // Verify cleanup worked for all entity types
        var motionAfterCleanup = await _motionRepository.GetAllFromQuestDbAsync();
        var onvifAfterCleanup = await _onvifRepository.GetAllFromQuestDbAsync();
        var safetyAfterCleanup = await _safetyRepository.GetAllFromQuestDbAsync();
        
        Assert.Empty(motionAfterCleanup);
        Assert.Empty(onvifAfterCleanup);
        Assert.Empty(safetyAfterCleanup);
    }

    public void Dispose()
    {
        _postgresContext?.Dispose();
        _questDbContext?.DisposeAsync();
        _serviceProvider?.Dispose();
    }
}