namespace PacketProcessing.Config;

using Serilog;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.AspNetCore.Hosting;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Services.Networking;
using System.Threading.Channels;
using Microsoft.Extensions.Logging;
using PacketProcessing.Repositories.InfluxRepository;
using Microsoft.Extensions.Options;
using PacketProcessing.Utils.Records;
using PacketProcessing.Services.Storage;
using PacketProcessing.Services.Orchestration;

/// <summary>
/// Configuration and Dependency Injection Manager
/// 
/// Registers all application services, middleware, and dependencies.
/// Follows layered architecture: Controllers → Services → Repositories → DbContext
/// </summary>
public class ConfigurationInjection
{
    /// <summary>
    /// Configures all application services and dependencies
    /// </summary>
    /// <param name="builder">The WebApplicationBuilder instance</param>
    public static void InjectConfigurations(WebApplicationBuilder builder)
    {
        // Configure Logging
        LoggingConfiguration.ConfigureLogging(builder);
        builder.Host.UseSerilog();

        // Configure all database services using unified DatabaseConfiguration
        DatabaseConfiguration.ConfigureServices(builder.Services, builder.Configuration);

        // Ensure DB is set up before services
        EnvironmentConfiguration.LoadConfigurations(builder);

        // Register Repositories & Services
        //TODO: Implement Repositories and Services

        var config = builder.Configuration;

        
        // === Channels ===
        builder.Services.AddSingleton(sp =>
        {
            var max = config.GetValue<int>("DataPipes:MotionCapture:Channel:Members", 1000000);
            return Channel.CreateBounded<MotionPacketEntity>(new BoundedChannelOptions(max)
            {
                FullMode = BoundedChannelFullMode.Wait
            });
        });

        builder.Services.AddSingleton(sp =>
        {
            var max = config.GetValue<int>("DataPipes:SafetyCapture:Channel:Members", 1000000);
            return Channel.CreateBounded<SafetyPacketEntity>(new BoundedChannelOptions(max)
            {
                FullMode = BoundedChannelFullMode.Wait
            });
        });

        builder.Services.AddSingleton(sp =>
        {
            var max = config.GetValue<int>("DataPipes:OnVIFCapture:Channel:Members", 100000);
            return Channel.CreateBounded<OnVIFPacketEntity>(new BoundedChannelOptions(max)
            {
                FullMode = BoundedChannelFullMode.Wait
            });
        });

        // === Handlers ===
        builder.Services.AddSingleton<HandlerService<MotionPacketEntity>>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<HandlerService<MotionPacketEntity>>>();
            var channel = sp.GetRequiredService<Channel<MotionPacketEntity>>();
            var repo = sp.GetRequiredService<IInfluxRepository<MotionPacketEntity>>();
            var opts = sp.GetRequiredService<IOptions<InfluxDbOptions>>();
            var cfg = sp.GetRequiredService<IConfiguration>();
            return new HandlerService<MotionPacketEntity>("DataPipes:MotionCapture", logger, channel, repo, opts, cfg);
        });

        builder.Services.AddSingleton<HandlerService<SafetyPacketEntity>>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<HandlerService<SafetyPacketEntity>>>();
            var channel = sp.GetRequiredService<Channel<SafetyPacketEntity>>();
            var repo = sp.GetRequiredService<IInfluxRepository<SafetyPacketEntity>>();
            var opts = sp.GetRequiredService<IOptions<InfluxDbOptions>>();
            var cfg = sp.GetRequiredService<IConfiguration>();
            return new HandlerService<SafetyPacketEntity>("DataPipes:SafetyCapture", logger, channel, repo, opts, cfg);
        });

        builder.Services.AddSingleton<HandlerService<OnVIFPacketEntity>>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<HandlerService<OnVIFPacketEntity>>>();
            var channel = sp.GetRequiredService<Channel<OnVIFPacketEntity>>();
            var repo = sp.GetRequiredService<IInfluxRepository<OnVIFPacketEntity>>();
            var opts = sp.GetRequiredService<IOptions<InfluxDbOptions>>();
            var cfg = sp.GetRequiredService<IConfiguration>();
            return new HandlerService<OnVIFPacketEntity>("DataPipes:OnVIFCapture", logger, channel, repo, opts, cfg);
        });

        // === Configuration ===
        builder.Services.Configure<InfluxDbOptions>(config.GetSection("Database"));

        // === Writers ===
        builder.Services.AddSingleton<IHostedService>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<DbWriterService<MotionPacketEntity>>>();
            var channel = sp.GetRequiredService<Channel<MotionPacketEntity>>();
            var repository = sp.GetRequiredService<IInfluxRepository<MotionPacketEntity>>();
            var options = sp.GetRequiredService<IOptions<InfluxDbOptions>>();
            var config = sp.GetRequiredService<IConfiguration>();
            return new DbWriterService<MotionPacketEntity>(logger, channel, repository, options, config);
        });
        
        builder.Services.AddSingleton<IHostedService>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<DbWriterService<SafetyPacketEntity>>>();
            var channel = sp.GetRequiredService<Channel<SafetyPacketEntity>>();
            var repository = sp.GetRequiredService<IInfluxRepository<SafetyPacketEntity>>();
            var options = sp.GetRequiredService<IOptions<InfluxDbOptions>>();
            var config = sp.GetRequiredService<IConfiguration>();
            return new DbWriterService<SafetyPacketEntity>(logger, channel, repository, options, config);
        });
        
        builder.Services.AddSingleton<IHostedService>(sp =>
        {
            var logger = sp.GetRequiredService<ILogger<DbWriterService<OnVIFPacketEntity>>>();
            var channel = sp.GetRequiredService<Channel<OnVIFPacketEntity>>();
            var repository = sp.GetRequiredService<IInfluxRepository<OnVIFPacketEntity>>();
            var options = sp.GetRequiredService<IOptions<InfluxDbOptions>>();
            var config = sp.GetRequiredService<IConfiguration>();
            return new DbWriterService<OnVIFPacketEntity>(logger, channel, repository, options, config);
        });

        // === Handlers as hosted background services ===
        builder.Services.AddSingleton<IHostedService>(sp => sp.GetRequiredService<HandlerService<MotionPacketEntity>>());
        builder.Services.AddSingleton<IHostedService>(sp => sp.GetRequiredService<HandlerService<SafetyPacketEntity>>());
        builder.Services.AddSingleton<IHostedService>(sp => sp.GetRequiredService<HandlerService<OnVIFPacketEntity>>());

        // === Orchestrator ===
        builder.Services.AddSingleton<IPipelineOrchestrator, PipelineOrchestrator>();

        // Device service
        builder.Services.AddSingleton<IDeviceService, DeviceService>();

        // Register Services (including CORS)
        CorsConfiguration.ConfigureCorsServices(builder.Services);

        // Register Health Checks
        builder.Services.AddHealthChecks();

        // Register Swagger & API Controllers
        builder.Services.AddEndpointsApiExplorer();
        builder.Services.AddSwaggerGen();
        builder.Services.AddControllers();
        
        // Configure routing to use lowercase URLs
        builder.Services.AddRouting(options => options.LowercaseUrls = true);
        
        // Configure Kestrel server limits
        builder.WebHost.ConfigureKestrel(options =>
        {
            options.Limits.MaxRequestBodySize = 200 * 1024 * 1024; // 200MB
            options.Limits.KeepAliveTimeout = TimeSpan.FromMinutes(10);
            options.Limits.RequestHeadersTimeout = TimeSpan.FromMinutes(5);
        });

        // Configure IIS options
        builder.Services.Configure<IISServerOptions>(options =>
        {
            options.MaxRequestBodySize = 200 * 1024 * 1024; // 200MB
        });
    }
    
    /// <summary>
    /// Configures all application middleware components
    /// </summary>
    /// <param name="app">The WebApplication instance</param>
    public static async Task InjectMiddlewareAsync(WebApplication app)
    {
        // Global exception handler should be first
        app.UseGlobalExceptionHandler();

        // Enable CORS Middleware
        CorsConfiguration.ConfigureCorsMiddleware(app);

        // Ensure databases are up to date before starting the application
        await DatabaseMigrationHelper.EnsureDatabasesUpToDateAsync(app);

        // Use Middleware (e.g., Swagger, HTTPS Redirection)
        if (!app.Environment.IsProduction())
        {
            app.UseSwagger();
            Log.Information("Swagger is enabled on route {Route}", app.Configuration.GetValue<string>("Application:Url")+"/swagger");
            app.UseSwaggerUI();
        }
        // Map simple health check endpoint
        app.MapHealthChecks("/health");
        
        app.MapControllers();
    }
    
    /// <summary>
    /// Configures all application middleware components (synchronous version for backward compatibility)
    /// </summary>
    /// <param name="app">The WebApplication instance</param>
    public static void InjectMiddleware(WebApplication app)
    {
        // Global exception handler should be first
        app.UseGlobalExceptionHandler();

        // Enable CORS Middleware
        CorsConfiguration.ConfigureCorsMiddleware(app);

        // Use Middleware (e.g., Swagger, HTTPS Redirection)
        if (!app.Environment.IsProduction())
        {
            app.UseSwagger();
            Log.Information("Swagger is enabled on route {Route}", app.Configuration.GetValue<string>("Application:Url")+"/swagger");
            app.UseSwaggerUI();
        }
        // Map simple health check endpoint
        app.MapHealthChecks("/health");
        
        app.MapControllers();
    }
}