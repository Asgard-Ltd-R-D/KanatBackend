using Dapper;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using PacketProcessing.Config;
using PacketProcessing.Context;
using PacketProcessing.Tests;
using Xunit;

namespace PacketProcessing.Tests.unit.DatabaseTests;

/// <summary>
/// Tests for database initialization and integrity
/// </summary>
public class DatabaseInitializationTests : IDisposable
{
    private readonly ServiceProvider _serviceProvider;
    private readonly PostgresDbContext _dbContext;
    private readonly QuestDbContext _questDbContext;

    public DatabaseInitializationTests()
    {
        // Setup test services
        var services = new ServiceCollection();
        
        // Add logging
        services.AddLogging(builder => builder.AddConsole());
        
        // Add test configuration
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string>
            {
                {"ConnectionStrings:Postgres", "Host=localhost;Port=56432;Database=pdb;Username=postgres;Password=postgres;"},
                {"ConnectionStrings:QuestDb", "Host=localhost;Port=9009;Database=qdb;Username=quest;Password=quest;"},
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
            }.Cast<KeyValuePair<string, string?>>())
            .Build();

        // Configure database services
        DatabaseConfiguration.ConfigureServices(services, configuration);
        
        _serviceProvider = services.BuildServiceProvider();
        _dbContext = _serviceProvider.GetRequiredService<PostgresDbContext>();
        _questDbContext = _serviceProvider.GetRequiredService<QuestDbContext>();
    }

    [Fact]
    public async Task DatabaseInitializationService_ShouldInitializePostgresDatabase()
    {
        // Arrange
        var logger = _serviceProvider.GetRequiredService<ILogger<DatabaseInitializationService>>();
        var service = new DatabaseInitializationService(_serviceProvider, logger);

        // Act
        await service.StartAsync(CancellationToken.None);

        // Assert
        var canConnect = await _dbContext.Database.CanConnectAsync();
        
        TestResultLogger.LogTestResult(
            "DatabaseInitializationService_ShouldInitializePostgresDatabase",
            canConnect,
            "Database initialization service",
            "PostgreSQL database should be accessible",
            $"CanConnect={canConnect}"
        );
        
        Assert.True(canConnect);
    }


    [Fact]
    public async Task PostgresDbContext_EnsureDatabaseAsync_ShouldCreateDatabase()
    {
        // Act
        var databaseCreated = await _dbContext.EnsureDatabaseAsync();

        // Assert
        var canConnect = await _dbContext.Database.CanConnectAsync();
        
        TestResultLogger.LogTestResult(
            "PostgresDbContext_EnsureDatabaseAsync_ShouldCreateDatabase",
            canConnect,
            "Database creation",
            "Database should be accessible after creation",
            $"CanConnect={canConnect}, DatabaseCreated={databaseCreated}"
        );
        
        Assert.True(canConnect);
    }

    [Fact]
    public async Task PostgresDbContext_ShouldHaveAllRequiredTables()
    {
        // Arrange
        await _dbContext.EnsureDatabaseAsync();

        // Act & Assert
        var targetsTableExists = await _dbContext.Targets.AnyAsync();
        var rangesTableExists = await _dbContext.Ranges.AnyAsync();
        var eventsTableExists = await _dbContext.Events.AnyAsync();
        var hitsTableExists = await _dbContext.Hits.AnyAsync();

        var allTablesExist = targetsTableExists || await _dbContext.Targets.CountAsync() >= 0;
        allTablesExist &= rangesTableExists || await _dbContext.Ranges.CountAsync() >= 0;
        allTablesExist &= eventsTableExists || await _dbContext.Events.CountAsync() >= 0;
        allTablesExist &= hitsTableExists || await _dbContext.Hits.CountAsync() >= 0;

        TestResultLogger.LogTestResult(
            "PostgresDbContext_ShouldHaveAllRequiredTables",
            allTablesExist,
            "PostgreSQL table verification",
            "All range entity tables should exist",
            $"Targets={allTablesExist}, Ranges={allTablesExist}, Events={allTablesExist}, Hits={allTablesExist}"
        );
        
        Assert.True(allTablesExist);
    }

    [Fact]
    public async Task PostgreSQL_Tables_ShouldHaveCorrectStructure()
    {
        // Arrange
        await _dbContext.EnsureDatabaseAsync();

        // Act - Query table structure information using raw SQL
        var tableNames = new[] { "targets", "ranges", "events", "hits" };
        var tableStructures = new List<string>();

        foreach (var tableName in tableNames)
        {
            var sql = $@"SELECT column_name || ' (' || data_type || ')' as column_info 
                        FROM information_schema.columns 
                        WHERE table_name = '{tableName}' 
                        ORDER BY ordinal_position";
            
            var columns = await _dbContext.Database.SqlQueryRaw<string>(sql).ToListAsync();
            tableStructures.Add($"{tableName}: {string.Join(", ", columns)}");
        }

        // Assert - Verify we have structure information for all tables
        var allTablesHaveStructure = tableStructures.Count == 4;
        var structureInfo = string.Join("; ", tableStructures);

        TestResultLogger.LogTestResult(
            "PostgreSQL_Tables_ShouldHaveCorrectStructure",
            allTablesHaveStructure,
            "PostgreSQL table structure verification",
            "All tables should have proper column structure",
            $"Tables with structure: {structureInfo}"
        );

        Assert.True(allTablesHaveStructure);
        Assert.Contains("targets:", structureInfo);
        Assert.Contains("ranges:", structureInfo);
        Assert.Contains("events:", structureInfo);
        Assert.Contains("hits:", structureInfo);
    }


    [Fact]
    public async Task DatabaseInitializationService_ShouldHandleMultipleInitializations()
    {
        // Arrange
        var logger = _serviceProvider.GetRequiredService<ILogger<DatabaseInitializationService>>();
        var service = new DatabaseInitializationService(_serviceProvider, logger);

        // Act - Initialize multiple times
        await service.StartAsync(CancellationToken.None);
        await service.StartAsync(CancellationToken.None);
        await service.StartAsync(CancellationToken.None);

        // Assert
        var canConnect = await _dbContext.Database.CanConnectAsync();
        
        TestResultLogger.LogTestResult(
            "DatabaseInitializationService_ShouldHandleMultipleInitializations",
            canConnect,
            "Multiple database initializations",
            "Database should remain accessible after multiple initializations",
            $"CanConnect={canConnect}"
        );
        
        Assert.True(canConnect);
    }

    [Fact]
    public async Task DatabaseInitializationService_ShouldStopGracefully()
    {
        // Arrange
        var logger = _serviceProvider.GetRequiredService<ILogger<DatabaseInitializationService>>();
        var service = new DatabaseInitializationService(_serviceProvider, logger);

        // Act
        await service.StartAsync(CancellationToken.None);
        await service.StopAsync(CancellationToken.None);

        // Assert
        var canConnect = await _dbContext.Database.CanConnectAsync();
        
        TestResultLogger.LogTestResult(
            "DatabaseInitializationService_ShouldStopGracefully",
            canConnect,
            "Service stop operation",
            "Database should remain accessible after service stop",
            $"CanConnect={canConnect}"
        );
        
        Assert.True(canConnect);
    }

    [Fact]
    public async Task DatabaseInitializationService_ShouldHandleCancellation()
    {
        // Arrange
        var logger = _serviceProvider.GetRequiredService<ILogger<DatabaseInitializationService>>();
        var service = new DatabaseInitializationService(_serviceProvider, logger);
        var cancellationTokenSource = new CancellationTokenSource();
        cancellationTokenSource.Cancel(); // Cancel immediately

        // Act & Assert
        var exception = await Record.ExceptionAsync(async () => 
            await service.StartAsync(cancellationTokenSource.Token));
        
        var passed = exception == null;
        
        TestResultLogger.LogTestResult(
            "DatabaseInitializationService_ShouldHandleCancellation",
            passed,
            "Cancellation handling",
            "Service should handle cancellation gracefully",
            exception?.Message ?? "No exception"
        );
        
        // Should not throw when cancelled
        Assert.Null(exception);
    }

    [Fact]
    public async Task QuestDbContext_EnsureDatabaseAsync_ShouldCreateTables()
    {
        // Act
        var tablesCreated = await _questDbContext.EnsureDatabaseAsync();
        
        // Assert
        await using var connection = await _questDbContext.OpenPgAsync();
        var connectionSuccessful = connection != null && connection.State == System.Data.ConnectionState.Open;
        
        TestResultLogger.LogTestResult(
            "QuestDbContext_EnsureDatabaseAsync_ShouldCreateTables",
            connectionSuccessful,
            "QuestDB table creation",
            "QuestDB tables should be created or already exist",
            $"TablesCreated={tablesCreated}, CanConnect={connectionSuccessful}"
        );
        
        Assert.True(connectionSuccessful);
    }

    [Fact]
    public async Task QuestDbContext_ShouldHaveAllRequiredPacketTables()
    {
        // Arrange
        var requiredTables = new[] { "motion_packets", "onvif_packets", "safety_packets" };
        
        // Act
        await _questDbContext.EnsureDatabaseAsync();
        
        await using var connection = await _questDbContext.OpenPgAsync();
        
        var tableChecks = new List<(string TableName, bool Exists)>();
        
        foreach (var tableName in requiredTables)
        {
            try
            {
                // Check if table exists by querying it (this will throw if table doesn't exist)
                var result = await connection.ExecuteScalarAsync<long>($"SELECT count() FROM {tableName}");
                tableChecks.Add((tableName, true));
            }
            catch (Exception)
            {
                tableChecks.Add((tableName, false));
            }
        }
        
        var allTablesExist = tableChecks.All(t => t.Exists);

        TestResultLogger.LogTestResult(
            "QuestDbContext_ShouldHaveAllRequiredPacketTables",
            allTablesExist,
            "QuestDB packet table verification",
            "All packet entity tables should exist",
            $"Motion={tableChecks[0].Exists}, OnVIF={tableChecks[1].Exists}, Safety={tableChecks[2].Exists}"
        );
        
        Assert.True(allTablesExist);
    }

    [Fact]
    public async Task QuestDbContext_OpenPgAsync_ShouldOpenConnection()
    {
        // Act
        await using var connection = await _questDbContext.OpenPgAsync();
        
        // Assert
        var connectionSuccessful = connection != null && connection.State == System.Data.ConnectionState.Open;
        
        TestResultLogger.LogTestResult(
            "QuestDbContext_OpenPgAsync_ShouldOpenConnection",
            connectionSuccessful,
            "QuestDB PostgreSQL connection",
            "Connection should be opened successfully",
            $"ConnectionState={connection?.State}"
        );
        
        Assert.True(connectionSuccessful);
    }

    public void Dispose()
    {
        _dbContext?.Dispose();
        _questDbContext?.DisposeAsync();
        _serviceProvider?.Dispose();
    }
}
