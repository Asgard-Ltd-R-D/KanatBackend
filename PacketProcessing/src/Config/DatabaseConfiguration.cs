using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using PacketProcessing.Context;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Entities.Range;
using PacketProcessing.Repositories;
using PacketProcessing.Utils.QuestDB;

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
    /// General database settings
    /// </summary>
    public GeneralDatabaseSettings General { get; set; } = new();

    /// <summary>
    /// Configures all database services in the service collection
    /// </summary>
    /// <param name="services">The service collection</param>
    /// <param name="configuration">The configuration</param>
    public static void ConfigureServices(IServiceCollection services, IConfiguration configuration)
    {
        // Configure PostgreSQL database
        ConfigurePostgresDatabase(services, configuration);
        
        // Configure QuestDB services
        ConfigureQuestDbServices(services, configuration);
        
        // Configure all repositories (packet and range)
        ConfigureRepositories(services, configuration);
        
        // Add database initialization service
        services.AddHostedService<DatabaseInitializationService>();
    }

    /// <summary>
    /// Configures PostgreSQL database services
    /// </summary>
    private static void ConfigurePostgresDatabase(IServiceCollection services, IConfiguration configuration)
    {
        // Configure PostgreSQL options
        services.Configure<PostgresConfiguration>(configuration.GetSection(PostgresConfiguration.SectionName));
        
        // Add PostgreSQL DbContext
        services.AddDbContext<AppDbContext>(options =>
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
    private static void ConfigureQuestDbServices(IServiceCollection services, IConfiguration configuration)
    {
        // Configure QuestDB options
        services.Configure<QuestDbConfiguration>(configuration.GetSection(QuestDbConfiguration.SectionName));
        
        // Get QuestDB connection string
        var questDbOptions = configuration.GetSection(QuestDbConfiguration.SectionName).Get<QuestDbConfiguration>();
        var questDbConnectionString = questDbOptions?.GetPostgresConnectionString() ?? 
                                    configuration.GetConnectionString("QuestDb") ?? 
                                    throw new InvalidOperationException("QuestDB connection string not found");
        
        // Register QuestDB table creator
        services.AddSingleton<QuestDbTableCreator>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<QuestDbTableCreator>>();
            return new QuestDbTableCreator(logger, questDbConnectionString);
        });
    }

    /// <summary>
    /// Configures all repository services (packet and range) to the service collection
    /// </summary>
    /// <param name="services">The service collection</param>
    /// <param name="configuration">The configuration</param>
    private static void ConfigureRepositories(IServiceCollection services, IConfiguration configuration)
    {
        // Register packet repositories (QuestDB)
        ConfigurePacketRepositories(services, configuration);
        
        // Register range repositories (PostgreSQL/EF Core)
        ConfigureRangeRepositories(services, configuration);
    }
    
    /// <summary>
    /// Configures packet repository services
    /// </summary>
    private static void ConfigurePacketRepositories(IServiceCollection services, IConfiguration configuration)
    {
        // Register specific packet repositories for convenience
        services.AddScoped<IPacketRepository<MotionPacketEntity>>(sp =>
        {
            var context = sp.GetRequiredService<AppDbContext>();
            var logger = sp.GetRequiredService<ILogger<PacketRepository<MotionPacketEntity>>>();
            var tableCreator = sp.GetRequiredService<QuestDbTableCreator>();
            var questDbConnectionString = tableCreator.GetConnectionString();
            return new PacketRepository<MotionPacketEntity>(context, logger, questDbConnectionString);
        });
        
        services.AddScoped<IPacketRepository<OnVIFPacketEntity>>(sp =>
        {
            var context = sp.GetRequiredService<AppDbContext>();
            var logger = sp.GetRequiredService<ILogger<PacketRepository<OnVIFPacketEntity>>>();
            var tableCreator = sp.GetRequiredService<QuestDbTableCreator>();
            var questDbConnectionString = tableCreator.GetConnectionString();
            return new PacketRepository<OnVIFPacketEntity>(context, logger, questDbConnectionString);
        });
        
        services.AddScoped<IPacketRepository<SafetyPacketEntity>>(sp =>
        {
            var context = sp.GetRequiredService<AppDbContext>();
            var logger = sp.GetRequiredService<ILogger<PacketRepository<SafetyPacketEntity>>>();
            var tableCreator = sp.GetRequiredService<QuestDbTableCreator>();
            var questDbConnectionString = tableCreator.GetConnectionString();
            return new PacketRepository<SafetyPacketEntity>(context, logger, questDbConnectionString);
        });
    }
    
    /// <summary>
    /// Configures range repository services to the service collection
    /// </summary>
    /// <param name="services">The service collection</param>
    /// <param name="configuration">The configuration</param>
    private static void ConfigureRangeRepositories(IServiceCollection services, IConfiguration configuration)
    {
        // Register specific range repositories for convenience
        services.AddScoped<IRangeRepository<RangeEntity>>(sp =>
        {
            var context = sp.GetRequiredService<AppDbContext>();
            var logger = sp.GetRequiredService<ILogger<RangeRepository<RangeEntity>>>();
            return new RangeRepository<RangeEntity>(context, logger);
        });
        
        services.AddScoped<IRangeRepository<EventEntity>>(sp =>
        {
            var context = sp.GetRequiredService<AppDbContext>();
            var logger = sp.GetRequiredService<ILogger<RangeRepository<EventEntity>>>();
            return new RangeRepository<EventEntity>(context, logger);
        });
        
        services.AddScoped<IRangeRepository<TargetEntity>>(sp =>
        {
            var context = sp.GetRequiredService<AppDbContext>();
            var logger = sp.GetRequiredService<ILogger<RangeRepository<TargetEntity>>>();
            return new RangeRepository<TargetEntity>(context, logger);
        });
        
        services.AddScoped<IRangeRepository<HitEntity>>(sp =>
        {
            var context = sp.GetRequiredService<AppDbContext>();
            var logger = sp.GetRequiredService<ILogger<RangeRepository<HitEntity>>>();
            return new RangeRepository<HitEntity>(context, logger);
        });
    }
}

/// <summary>
/// PostgreSQL database configuration for range entities
/// </summary>
public class PostgresConfiguration
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
public class QuestDbConfiguration
{
    public const string SectionName = "QuestDb";
    
    /// <summary>
    /// QuestDB server hostname or IP address
    /// </summary>
    public string Host { get; set; } = "localhost";
    
    /// <summary>
    /// QuestDB PostgreSQL wire protocol port
    /// </summary>
    public int PostgresPort { get; set; } = 9009;
    
    /// <summary>
    /// QuestDB InfluxDB line protocol port
    /// </summary>
    public int InfluxPort { get; set; } = 9000;
    
    /// <summary>
    /// QuestDB HTTP port
    /// </summary>
    public int HttpPort { get; set; } = 8812;
    
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
        return $"http://{Host}:{InfluxPort}";
    }
    
    /// <summary>
    /// Gets the QuestDB HTTP connection string
    /// </summary>
    /// <returns>The formatted connection string</returns>
    public string GetHttpConnectionString()
    {
        return $"http://{Host}:{HttpPort}";
    }
}

/// <summary>
/// General database settings
/// </summary>
public class GeneralDatabaseSettings
{
    /// <summary>
    /// Whether to enable automatic database initialization on startup
    /// </summary>
    public bool EnableAutoInitialization { get; set; } = true;
    
    /// <summary>
    /// Whether to enable database migration on startup
    /// </summary>
    public bool EnableMigrations { get; set; } = true;
    
    /// <summary>
    /// Whether to enable detailed database logging
    /// </summary>
    public bool EnableDetailedLogging { get; set; } = true;
    
    /// <summary>
    /// Maximum retry attempts for database operations
    /// </summary>
    public int MaxRetryAttempts { get; set; } = 3;
    
    /// <summary>
    /// Delay between retry attempts in seconds
    /// </summary>
    public int RetryDelaySeconds { get; set; } = 5;
}

/// <summary>
/// Service for initializing both PostgreSQL and QuestDB databases
/// </summary>
public class DatabaseInitializationService : IHostedService
{
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<DatabaseInitializationService> _logger;

    public DatabaseInitializationService(
        IServiceProvider serviceProvider,
        ILogger<DatabaseInitializationService> logger)
    {
        _serviceProvider = serviceProvider ?? throw new ArgumentNullException(nameof(serviceProvider));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    /// <summary>
    /// Starts the database initialization service
    /// </summary>
    /// <param name="cancellationToken">Cancellation token</param>
    public async Task StartAsync(CancellationToken cancellationToken)
    {
        try
        {
            _logger.LogInformation("Starting database initialization...");
            
            using var scope = _serviceProvider.CreateScope();
            
            // Initialize PostgreSQL database (range entities)
            await InitializePostgresDatabaseAsync(scope);
            
            // Initialize QuestDB database (packet entities)
            await InitializeQuestDbDatabaseAsync(scope);
            
            _logger.LogInformation("Database initialization completed successfully");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "An error occurred during database initialization");
            throw;
        }
    }

    /// <summary>
    /// Stops the database initialization service
    /// </summary>
    /// <param name="cancellationToken">Cancellation token</param>
    public Task StopAsync(CancellationToken cancellationToken)
    {
        _logger.LogInformation("Database initialization service stopped");
        return Task.CompletedTask;
    }

    /// <summary>
    /// Initializes the PostgreSQL database for range entities
    /// </summary>
    /// <param name="scope">Service scope</param>
    private async Task InitializePostgresDatabaseAsync(IServiceScope scope)
    {
        try
        {
            _logger.LogInformation("Initializing PostgreSQL database for range entities...");
            
            var dbContext = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            var databaseCreated = await dbContext.EnsureDatabaseAsync();
            
            if (databaseCreated)
            {
                _logger.LogInformation("PostgreSQL database and tables created successfully");
            }
            else
            {
                _logger.LogInformation("PostgreSQL database already exists");
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "An error occurred while initializing PostgreSQL database");
            throw;
        }
    }

    /// <summary>
    /// Initializes the QuestDB database for packet entities
    /// </summary>
    /// <param name="scope">Service scope</param>
    private async Task InitializeQuestDbDatabaseAsync(IServiceScope scope)
    {
        try
        {
            _logger.LogInformation("Initializing QuestDB database for packet entities...");
            
            var tableCreator = scope.ServiceProvider.GetRequiredService<QuestDbTableCreator>();
            var tablesCreated = await tableCreator.EnsureTablesExistAsync();
            
            if (tablesCreated)
            {
                _logger.LogInformation("QuestDB tables created successfully");
            }
            else
            {
                _logger.LogInformation("QuestDB tables already exist");
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "An error occurred while initializing QuestDB database");
            throw;
        }
    }
}
