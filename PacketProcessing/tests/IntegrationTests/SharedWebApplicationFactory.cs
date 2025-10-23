using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using PacketProcessing.Config;
using PacketProcessing.Context;
using PacketProcessing.Repositories.EfRepository;
using PacketProcessing.Repositories.InfluxRepository;
using PacketProcessing.Services;
using PacketProcessing.Services.Realtime;
using PacketProcessing.Services.Transmission;
using PacketProcessing.Services.Playback;
using Microsoft.Extensions.Configuration;
using Microsoft.EntityFrameworkCore;
using System.Data.Common;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Xunit;
using Npgsql;

namespace PacketProcessing.IntegrationTests;

/// <summary>
/// Shared WebApplicationFactory for integration tests to avoid creating multiple instances
/// </summary>
public class SharedWebApplicationFactory : WebApplicationFactory<ConfigurationInjection>
{
    private bool _disposed = false;
    
    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.ConfigureServices(services =>
        {
            // Remove the real database contexts
            var dbContextDescriptor = services.SingleOrDefault(
                d => d.ServiceType == typeof(DbContextOptions<PostgresDbContext>));
            if (dbContextDescriptor != null)
                services.Remove(dbContextDescriptor);

            // Remove QuestDbContext registration if it exists
            var questDbContextDescriptor = services.SingleOrDefault(
                d => d.ServiceType == typeof(QuestDbContext));
            if (questDbContextDescriptor != null)
                services.Remove(questDbContextDescriptor);

            // Add in-memory database for testing
            services.AddDbContext<PostgresDbContext>(options =>
            {
                options.UseInMemoryDatabase("TestPostgresDb");
            });

            // Register QuestDbContext for integration tests
            services.AddSingleton<QuestDbContext>(provider =>
            {
                var configuration = provider.GetRequiredService<IConfiguration>();
                var logger = provider.GetRequiredService<ILogger<QuestDbContext>>();
                return new QuestDbContext(configuration, logger);
            });

            // Configure test-specific services
            ConfigureTestServices(services);
        });

        builder.UseEnvironment("Test");
        builder.ConfigureLogging(logging =>
        {
            logging.ClearProviders();
            logging.SetMinimumLevel(LogLevel.Warning);
        });
        
        // Configure test-specific configuration
        builder.ConfigureAppConfiguration(config =>
        {
            config.AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["SkipDatabaseInitialization"] = "true"
            });
        });
    }

    protected virtual void ConfigureTestServices(IServiceCollection services)
    {
        // Override services for testing if needed
        // For example, you might want to mock certain services
    }


    public override async ValueTask DisposeAsync()
    {
        if (!_disposed)
        {
            using var scope = Services.CreateScope();
            var postgresContext = scope.ServiceProvider.GetRequiredService<PostgresDbContext>();
            
            await postgresContext.Database.EnsureDeletedAsync();
            
            _disposed = true;
        }
        
        await base.DisposeAsync();
    }

    protected override void Dispose(bool disposing)
    {
        if (!_disposed)
        {
            _disposed = true;
        }
        base.Dispose(disposing);
    }
}

