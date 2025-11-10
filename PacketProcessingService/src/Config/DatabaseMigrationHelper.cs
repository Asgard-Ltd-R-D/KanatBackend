using Microsoft.AspNetCore.Builder;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using PacketProcessing.Context;

namespace PacketProcessing.Config;

/// <summary>
/// Simplified Database Migration Helper
/// Ensures both PostgreSQL and QuestDB are properly initialized and migrated
/// </summary>
public static class DatabaseMigrationHelper
{
    /// <summary>
    /// Ensures all databases are up to date with the latest migrations and table structures
    /// </summary>
    /// <param name="app">The WebApplication instance</param>
    public static async Task EnsureDatabasesUpToDateAsync(WebApplication app)
    {
        var loggerFactory = app.Services.GetRequiredService<ILoggerFactory>();
        var logger = loggerFactory.CreateLogger("DatabaseMigrationHelper");
        
        try
        {
            logger.LogInformation("=== DATABASE INITIALIZATION STARTED ===");
            
            using var scope = app.Services.CreateScope();
            
            // Initialize PostgreSQL database (range entities)
            await InitializePostgresDatabaseAsync(scope, logger);
            
            // Initialize QuestDB database (packet entities)
            await InitializeQuestDbDatabaseAsync(scope, logger);
            
            logger.LogInformation("=== DATABASE INITIALIZATION COMPLETED ===");
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "=== DATABASE INITIALIZATION FAILED ===");
            throw;
        }
    }

    /// <summary>
    /// Initialize PostgreSQL database with Entity Framework migrations
    /// </summary>
    private static async Task InitializePostgresDatabaseAsync(IServiceScope scope, ILogger logger)
    {
        try
        {
            logger.LogInformation("Initializing PostgreSQL database...");
            
            var postgresContext = scope.ServiceProvider.GetRequiredService<PostgresDbContext>();
            
            // Ensure database is created
            await postgresContext.Database.EnsureCreatedAsync();
            
            // Apply any pending migrations
            var pendingMigrations = await postgresContext.Database.GetPendingMigrationsAsync();
            if (pendingMigrations.Any())
            {
                logger.LogInformation("Applying {Count} pending PostgreSQL migrations...", pendingMigrations.Count());
                await postgresContext.Database.MigrateAsync();
                logger.LogInformation("PostgreSQL migrations applied successfully");
            }
            else
            {
                logger.LogInformation("PostgreSQL database is up to date - no migrations needed");
            }
            
            // Verify connection
            var canConnect = await postgresContext.Database.CanConnectAsync();
            if (canConnect)
            {
                logger.LogInformation("PostgreSQL database connection verified successfully");
            }
            else
            {
                throw new InvalidOperationException("PostgreSQL database connection failed");
            }
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to initialize PostgreSQL database");
            throw;
        }
    }

    /// <summary>
    /// Initialize QuestDB database and ensure tables exist
    /// </summary>
    private static async Task InitializeQuestDbDatabaseAsync(IServiceScope scope, ILogger logger)
    {
        try
        {
            logger.LogInformation("Initializing QuestDB database...");
            
            var questContext = scope.ServiceProvider.GetRequiredService<QuestDbContext>();
            
            // Ensure database and tables are created
            await questContext.EnsureDatabaseAsync();
            
            logger.LogInformation("QuestDB database initialization completed successfully");
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to initialize QuestDB database");
            throw;
        }
    }
}