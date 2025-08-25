using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.AspNetCore.Builder;
using PacketProcessing.Context;
using Microsoft.EntityFrameworkCore;

namespace PacketProcessing.Config;

/// <summary>
/// Database Migration Helper
/// 
/// Handles database initialization, migration, and verification in a step-by-step process.
/// Ensures the database is properly set up before the application starts.
/// </summary>
public static class DatabaseMigrationHelper
{
    /// <summary>
    /// Ensures the database is up to date with the latest migrations
    /// </summary>
    /// <param name="app">The WebApplication instance</param>
    public static async Task EnsureDatabaseUpToDateAsync(WebApplication app)
    {
        var loggerFactory = app.Services.GetRequiredService<ILoggerFactory>();
        var logger = loggerFactory.CreateLogger("DatabaseMigrationHelper");
        
        try
        {
            logger.LogInformation("Starting database initialization process...");
            
            // Step 1: Create a service scope
            using var scope = app.Services.CreateScope();
            var dbContext = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            
            // Step 2: Ensure database and tables are created
            logger.LogInformation("Step 1: Initializing database and tables...");
            await dbContext.EnsureDatabaseAsync();
            
            // Step 3: Verify all required tables exist
            logger.LogInformation("Step 2: Verifying table structure...");
            await VerifyDatabaseStructureAsync(dbContext, logger);
            
            logger.LogInformation("Database initialization completed successfully!");
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Database initialization failed!");
            throw;
        }
    }
    
    /// <summary>
    /// Verifies that all required database tables exist and are accessible
    /// </summary>
    /// <param name="dbContext">The database context</param>
    /// <param name="logger">The logger instance</param>
    private static async Task VerifyDatabaseStructureAsync(AppDbContext dbContext, ILogger logger)
    {
        try
        {
            // Verify each entity table exists and is accessible
            var motionPacketsCount = await dbContext.MotionPackets.CountAsync();
            logger.LogInformation("✓ Motion packets table verified (Count: {Count})", motionPacketsCount);
            
            var onvifPacketsCount = await dbContext.OnVifPackets.CountAsync();
            logger.LogInformation("✓ OnVIF packets table verified (Count: {Count})", onvifPacketsCount);
            
            var safetyPacketsCount = await dbContext.SafetyPackets.CountAsync();
            logger.LogInformation("✓ Safety packets table verified (Count: {Count})", safetyPacketsCount);
            
            logger.LogInformation("All database tables verified successfully!");
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to verify database structure!");
            throw;
        }
    }
}