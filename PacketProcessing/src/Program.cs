
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using PacketProcessing.Config;
using System.Linq;
using System.Text.Json;

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

// Check if database initialization should be skipped (e.g., for testing)
var skipDatabaseInitialization = app.Configuration.GetValue<bool>("SkipDatabaseInitialization");
if (skipDatabaseInitialization)
{
    dbLogger.LogInformation("Skipping database initialization (SkipDatabaseInitialization is true)");
}
else
{
    try
    {
        dbLogger.LogInformation("Starting database initialization and migration...");
        await DatabaseMigrationHelper.EnsureDatabasesUpToDateAsync(app);
        dbLogger.LogInformation("Database initialization and migration completed successfully!\n");
    }
    catch (Exception ex)
    {
        dbLogger.LogError(ex, "Database initialization and migration failed!");
        throw;
    }
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
logger.LogInformation("Content Root: {ContentRoot}\n", builder.Environment.ContentRootPath);

// Log key configuration values
logger.LogInformation("=== CONFIGURATION ===");
logger.LogInformation("ASPNETCORE_ENVIRONMENT: {AspNetCoreEnvironment}", builder.Environment.EnvironmentName);
logger.LogInformation("ASPNETCORE_URLS: {AspNetCoreUrls}\n", configuration["ASPNETCORE_URLS"]);

// Log database configurations from DatabaseConfiguration classes
var postgresConfig = configuration.GetSection(PostgresConfiguration.SectionName).Get<PostgresConfiguration>();
if (postgresConfig != null)
{
    logger.LogInformation("=== POSTGRESQL CONFIGURATION ===");
    logger.LogInformation("PostgreSQL Host: {Host}", postgresConfig.Host);
    logger.LogInformation("PostgreSQL Port: {Port}", postgresConfig.Port);
    logger.LogInformation("PostgreSQL Database: {Database}", postgresConfig.Database);
    logger.LogInformation("PostgreSQL Username: {Username}", postgresConfig.Username);
    logger.LogInformation("PostgreSQL Connection String: {Connection}\n", 
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
    logger.LogInformation("QuestDB PostgreSQL Connection: {Connection}\n", 
        questDbConfig.GetPostgresConnectionString().Replace("Password=quest", "Password=***"));
}

// Log Concurrency and DataPipes sections from appsettings.json
logger.LogInformation("=== CONCURRENCY CONFIGURATION ===");
var concurrencySection = configuration.GetSection("Concurrency");
foreach (var kv in concurrencySection.AsEnumerable(makePathsRelative: true))
{
    if (string.IsNullOrEmpty(kv.Value)) continue;
    var key = kv.Key;
    if (key.StartsWith("Concurrency:")) key = key["Concurrency:".Length..];
    if (key == "Concurrency") continue;
    logger.LogInformation("{Key} = {Value}", key, kv.Value);
}

logger.LogInformation("\n");
logger.LogInformation("=== DATAPIPES CONFIGURATION ===");
var dataPipes = configuration.GetSection("DataPipes");
foreach (var pipe in dataPipes.GetChildren())
{
    var name = pipe.Key;
    var protocol = pipe.GetSection("Network").GetValue<string>("Protocol");
    var device = pipe.GetSection("Network").GetValue<string>("Device");
    var ips = pipe.GetSection("Network").GetSection("IPs").Get<string[]>() ?? [];
    var members = pipe.GetSection("Channel").GetValue<int?>("Members");
    var intervalMs = pipe.GetSection("Sampling").GetValue<int?>("IntervalMs");

    var payload = new
    {
        Protocol = protocol,
        IPs = ips.Length > 0 ? ips : null,
        Device = device,
        Members = members,
        IntervalMs = intervalMs
    };

    var json = JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = false, DefaultIgnoreCondition = System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull });
    logger.LogInformation("{Pipeline} = {Json}", name, json);
}

logger.LogInformation("\n");
logger.LogInformation("=== APPLICATION READY ===");

/// <summary>
/// Start the web application
/// </summary>
app.Run();