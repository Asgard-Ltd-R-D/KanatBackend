
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using PacketProcessing.Config;

var builder = WebApplication.CreateBuilder(args);

/// <summary>
/// Configure all application services and dependencies
/// </summary>
ConfigurationInjection.InjectConfigurations(builder);

var app = builder.Build();

/// <summary>
/// Ensure database is up to date with latest migrations
/// </summary>
var loggerFactory = app.Services.GetRequiredService<ILoggerFactory>();
var dbLogger = loggerFactory.CreateLogger("DatabaseMigrationHelper");
try
{
    dbLogger.LogInformation("Starting database initialization and migration...");
    await DatabaseMigrationHelper.EnsureDatabasesUpToDateAsync(app);
    dbLogger.LogInformation("Database initialization and migration completed successfully!");
}
catch (Exception ex)
{
    dbLogger.LogError(ex, "Database initialization and migration failed!");
    throw;
}

/// <summary>
/// Configure all middleware components
/// </summary>
ConfigurationInjection.InjectMiddleware(app);

/// <summary>
/// Log application environment and configurations
/// </summary>
var logger = app.Services.GetRequiredService<ILogger<Program>>();
var configuration = app.Services.GetRequiredService<IConfiguration>();

logger.LogInformation("=== APPLICATION STARTUP ===");
logger.LogInformation("Environment: {Environment}", builder.Environment.EnvironmentName);
logger.LogInformation("Application Name: {ApplicationName}", builder.Environment.ApplicationName);
logger.LogInformation("Content Root: {ContentRoot}", builder.Environment.ContentRootPath);

// Log key configuration values
logger.LogInformation("=== CONFIGURATION ===");
logger.LogInformation("ASPNETCORE_ENVIRONMENT: {AspNetCoreEnvironment}", builder.Environment.EnvironmentName);
logger.LogInformation("ASPNETCORE_URLS: {AspNetCoreUrls}", configuration["ASPNETCORE_URLS"]);

// Log database configurations from DatabaseConfiguration classes
var postgresConfig = configuration.GetSection(PostgresConfiguration.SectionName).Get<PostgresConfiguration>();
if (postgresConfig != null)
{
    logger.LogInformation("=== POSTGRESQL CONFIGURATION ===");
    logger.LogInformation("PostgreSQL Host: {Host}", postgresConfig.Host);
    logger.LogInformation("PostgreSQL Port: {Port}", postgresConfig.Port);
    logger.LogInformation("PostgreSQL Database: {Database}", postgresConfig.Database);
    logger.LogInformation("PostgreSQL Username: {Username}", postgresConfig.Username);
    logger.LogInformation("PostgreSQL Connection String: {Connection}", 
        postgresConfig.GetConnectionString().Replace("Password=postgres", "Password=***"));
}

var questDbConfig = configuration.GetSection(QuestDbConfiguration.SectionName).Get<QuestDbConfiguration>();
if (questDbConfig != null)
{
    logger.LogInformation("=== QUESTDB CONFIGURATION ===");
    logger.LogInformation("QuestDB Host: {Host}", questDbConfig.Host);
    logger.LogInformation("QuestDB PostgreSQL Port: {PostgresPort}", questDbConfig.PostgresPort);
    logger.LogInformation("QuestDB Influx Port: {InfluxPort}", questDbConfig.InfluxPort);
    logger.LogInformation("QuestDB HTTP Port: {HttpPort}", questDbConfig.HttpPort);
    logger.LogInformation("QuestDB Username: {Username}", questDbConfig.Username);
    logger.LogInformation("QuestDB Database: {Database}", questDbConfig.Database);
    logger.LogInformation("QuestDB PostgreSQL Connection: {Connection}", 
        questDbConfig.GetPostgresConnectionString().Replace("Password=quest", "Password=***"));
}

// Log capture configuration
var captureMode = configuration["Capture:Mode"];
var readTimeoutMs = configuration["Capture:ReadTimeoutMs"];
var kernelBufferMb = configuration["Capture:KernelBufferMb"];
var logEveryMs = configuration["Capture:LogEveryMs"];

logger.LogInformation("=== CAPTURE CONFIGURATION ===");
logger.LogInformation("Capture Mode: {CaptureMode}", captureMode);
logger.LogInformation("Read Timeout: {ReadTimeoutMs}ms", readTimeoutMs);
logger.LogInformation("Kernel Buffer: {KernelBufferMb}MB", kernelBufferMb);
logger.LogInformation("Log Interval: {LogEveryMs}ms", logEveryMs);

logger.LogInformation("=== APPLICATION READY ===");

/// <summary>
/// Start the web application
/// </summary>
app.Run();