using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using PacketProcessing.Context;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories;

namespace PacketProcessing.Config;

/// <summary>
/// Extension methods for configuring database services
/// </summary>
public static class DatabaseServiceExtensions
{
    /// <summary>
    /// Adds PostgreSQL database services to the service collection
    /// </summary>
    /// <param name="services">The service collection</param>
    /// <param name="configuration">The configuration</param>
    /// <returns>The service collection for chaining</returns>
    public static IServiceCollection AddPostgresDatabase(this IServiceCollection services, IConfiguration configuration)
    {
        // Configure PostgreSQL options
        services.Configure<PostgresOptions>(configuration.GetSection(PostgresOptions.SectionName));
        
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
        
        return services;
    }
    
    /// <summary>
    /// Adds QuestDB services to the service collection
    /// </summary>
    /// <param name="services">The service collection</param>
    /// <param name="configuration">The configuration</param>
    /// <returns>The service collection for chaining</returns>
    public static IServiceCollection AddQuestDbServices(this IServiceCollection services, IConfiguration configuration)
    {
        // Configure QuestDB options
        services.Configure<QuestDbOptions>(configuration.GetSection(QuestDbOptions.SectionName));
        
        return services;
    }
    
    /// <summary>
    /// Adds packet repository services to the service collection
    /// </summary>
    /// <param name="services">The service collection</param>
    /// <param name="configuration">The configuration</param>
    /// <returns>The service collection for chaining</returns>
    public static IServiceCollection AddPacketRepositories(this IServiceCollection services, IConfiguration configuration)
    {
        // Get QuestDB connection string
        var questDbOptions = configuration.GetSection(QuestDbOptions.SectionName).Get<QuestDbOptions>();
        var questDbConnectionString = questDbOptions?.GetPostgresConnectionString() ?? 
                                    configuration.GetConnectionString("QuestDb") ?? 
                                    throw new InvalidOperationException("QuestDB connection string not found");
        
        // Register specific packet repositories for convenience
        services.AddScoped<IPacketRepository<MotionPacketEntity>>(sp =>
        {
            var context = sp.GetRequiredService<AppDbContext>();
            var logger = sp.GetRequiredService<ILogger<PacketRepository<MotionPacketEntity>>>();
            return new PacketRepository<MotionPacketEntity>(context, logger, questDbConnectionString);
        });
        
        services.AddScoped<IPacketRepository<OnVIFPacketEntity>>(sp =>
        {
            var context = sp.GetRequiredService<AppDbContext>();
            var logger = sp.GetRequiredService<ILogger<PacketRepository<OnVIFPacketEntity>>>();
            return new PacketRepository<OnVIFPacketEntity>(context, logger, questDbConnectionString);
        });
        
        services.AddScoped<IPacketRepository<SafetyPacketEntity>>(sp =>
        {
            var context = sp.GetRequiredService<AppDbContext>();
            var logger = sp.GetRequiredService<ILogger<PacketRepository<SafetyPacketEntity>>>();
            return new PacketRepository<SafetyPacketEntity>(context, logger, questDbConnectionString);
        });
        
        return services;
    }
    
    /// <summary>
    /// Adds all database services (PostgreSQL, QuestDB, and repositories) to the service collection
    /// </summary>
    /// <param name="services">The service collection</param>
    /// <param name="configuration">The configuration</param>
    /// <returns>The service collection for chaining</returns>
    public static IServiceCollection AddDatabaseServices(this IServiceCollection services, IConfiguration configuration)
    {
        return services
            .AddPostgresDatabase(configuration)
            .AddQuestDbServices(configuration)
            .AddPacketRepositories(configuration);
    }
}
