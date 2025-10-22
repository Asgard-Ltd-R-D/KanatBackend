using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using PacketProcessing.Context;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Entities.Range;
using PacketProcessing.Repositories.EfRepository;
using PacketProcessing.Repositories.InfluxRepository;

namespace PacketProcessing.Config;

/// <summary>
/// Unified database configuration and initialization for PostgreSQL and QuestDB
/// </summary>
public class DatabaseConfiguration
{
    /// <summary>
    /// PostgreSQL database configuration for range entities (Entity Framework)
    /// </summary>
    public PostgresConfiguration Postgres { get; set; } = new();
    
    /// <summary>
    /// QuestDB configuration for packet entities (Time-series database)
    /// </summary>
    public QuestDbConfiguration QuestDb { get; set; } = new();

    /// <summary>
    /// Configures all database services in the service collection
    /// </summary>
    /// <param name="services">The service collection</param>
    /// <param name="configuration">The configuration</param>
    public static void ConfigureServices(IServiceCollection services, IConfiguration configuration)
    {
        // Configure PostgreSQL context
        ConfigurePostgresdbContext(services, configuration);
        
        // Configure QuestDB context
        ConfigureQuestDbContext(services, configuration);
        
        // Configure all repositories (packet and range)
        ConfigureRepositories(services, configuration);
    }

    /// <summary>
    /// Configures PostgreSQL database services
    /// </summary>
    private static void ConfigurePostgresdbContext(IServiceCollection services, IConfiguration configuration)
    {
        // Configure PostgreSQL options
        services.Configure<PostgresConfiguration>(configuration.GetSection(PostgresConfiguration.SectionName));
        
        // Add PostgreSQL DbContext
        services.AddDbContext<PostgresDbContext>(options =>
        {
            var connectionString = configuration.GetConnectionString("Postgres");
            options.UseNpgsql(connectionString, npgsqlOptions =>
            {
                npgsqlOptions.EnableRetryOnFailure(
                    maxRetryCount: 3,
                    maxRetryDelay: TimeSpan.FromSeconds(30),
                    errorCodesToAdd: null);
            });
        });
    }

    /// <summary>
    /// Configures QuestDB services
    /// </summary>
    private static void ConfigureQuestDbContext(IServiceCollection services, IConfiguration configuration)
    {
        // Configure QuestDB options
        services.Configure<QuestDbConfiguration>(configuration.GetSection(QuestDbConfiguration.SectionName));
        
        // Register QuestDbContext
        services.AddSingleton<QuestDbContext>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<QuestDbContext>>();
            return new QuestDbContext(configuration, logger);
        });
    }

    /// <summary>
    /// Configures all repository services to the service collection
    /// </summary>
    /// <param name="services">The service collection</param>
    /// <param name="configuration">The configuration</param>
    private static void ConfigureRepositories(IServiceCollection services, IConfiguration configuration)
    {
        // Register packet repositories (QuestDB)
        ConfigurePacketRepositories(services, configuration);
        ConfigureRangeRepositories(services, configuration);
    }

    private static void ConfigureRangeRepositories(IServiceCollection services, IConfiguration configuration)
    {
        // Register range repositories (PostgreSQL)
        services.AddSingleton<IEfRepository<RangeEntity>>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<EfRepository<RangeEntity>>>();
            var dbContext = sp.GetRequiredService<PostgresDbContext>();
            return new EfRepository<RangeEntity>(dbContext, logger);
        });

        services.AddSingleton<IEfRepository<EventEntity>>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<EfRepository<EventEntity>>>();
            var dbContext = sp.GetRequiredService<PostgresDbContext>();
            return new EfRepository<EventEntity>(dbContext, logger);
        });

        services.AddSingleton<IEfRepository<TargetEntity>>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<EfRepository<TargetEntity>>>();
            var dbContext = sp.GetRequiredService<PostgresDbContext>();
            return new EfRepository<TargetEntity>(dbContext, logger);
        });
    }
    
    /// <summary>
    /// Configures packet repository services
    /// </summary>
    private static void ConfigurePacketRepositories(IServiceCollection services, IConfiguration configuration)
    {
        // Register specific packet repositories for convenience
        services.AddSingleton<IInfluxRepository<MotionPacketEntity>>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<InfluxRepository<MotionPacketEntity>>>();
            var questDbContext = sp.GetRequiredService<QuestDbContext>();
            return new InfluxRepository<MotionPacketEntity>(logger, questDbContext);
        });
        
        services.AddSingleton<IInfluxRepository<OnVIFPacketEntity>>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<InfluxRepository<OnVIFPacketEntity>>>();
            var questDbContext = sp.GetRequiredService<QuestDbContext>();
            return new InfluxRepository<OnVIFPacketEntity>(logger, questDbContext);
        });
        
        services.AddSingleton<IInfluxRepository<SafetyPacketEntity>>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<InfluxRepository<SafetyPacketEntity>>>();
            var questDbContext = sp.GetRequiredService<QuestDbContext>();
            return new InfluxRepository<SafetyPacketEntity>(logger, questDbContext);
        });
    }
}

/// <summary>
/// PostgreSQL database configuration for range entities
/// </summary>
public record PostgresConfiguration
{
    public const string SectionName = "Postgres";
    
    /// <summary>
    /// PostgreSQL server hostname or IP address
    /// </summary>
    public string Host { get; set; } = "localhost";
    
    /// <summary>
    /// PostgreSQL server port
    /// </summary>
    public int Port { get; set; } = 5432;
    
    /// <summary>
    /// Database name
    /// </summary>
    public string Database { get; set; } = "pdb";
    
    /// <summary>
    /// Database username
    /// </summary>
    public string Username { get; set; } = "postgres";
    
    /// <summary>
    /// Database password
    /// </summary>
    public string Password { get; set; } = "postgres";
    
    /// <summary>
    /// Gets the PostgreSQL connection string
    /// </summary>
    /// <returns>The formatted connection string</returns>
    public string GetConnectionString()
    {
        return $"Host={Host};Port={Port};Database={Database};Username={Username};Password={Password};" +
               "Include Error Detail=true;";
    }
}

/// <summary>
/// QuestDB configuration for packet entities
/// </summary>
public record QuestDbConfiguration
{
    public const string SectionName = "QuestDb";
    
    /// <summary>
    /// QuestDB server hostname or IP address
    /// </summary>
    public string Host { get; set; } = "localhost";
    
    /// <summary>
    /// QuestDB PostgreSQL wire protocol port
    /// </summary>
    public int PostgresPort { get; set; } = 8812;
    
    /// <summary>
    /// QuestDB InfluxDB line protocol port
    /// </summary>
    public int InfluxPort { get; set; } = 9000;
    
    /// <summary>
    /// QuestDB HTTP port
    /// </summary>
    public int HttpPort { get; set; } = 9009;
    
    /// <summary>
    /// Database username
    /// </summary>
    public string Username { get; set; } = "quest";
    
    /// <summary>
    /// Database password
    /// </summary>
    public string Password { get; set; } = "quest";
    
    /// <summary>
    /// Database name
    /// </summary>
    public string Database { get; set; } = "qdb";

    /// <summary>
    /// Max rows to buffer before flushing (auto_flush_rows)
    /// </summary>
    public int BatchSize { get; init; } = 1000;

    /// <summary>
    /// Timeout (ms) before forcing flush even if batch not full (auto_flush_interval)
    /// </summary>
    public int BatchTimeoutMs { get; init; } = 30;
    
    /// <summary>
    /// Gets the QuestDB PostgreSQL connection string
    /// </summary>
    /// <returns>The formatted connection string</returns>
    public string GetPostgresConnectionString()
    {
        return $"Host={Host};Port={PostgresPort};Database={Database};Username={Username};Password={Password};" +
               "Include Error Detail=true;";
    }
    
    /// <summary>
    /// Gets the QuestDB InfluxDB line protocol connection string
    /// </summary>
    /// <returns>The formatted connection string</returns>
    public string GetInfluxConnectionString()
    {
        return $"http::addr={Host}:{InfluxPort};username={Username};password={Password};" + 
               $"auto_flush_rows={BatchSize};auto_flush_interval={BatchTimeoutMs};";
    }
}

