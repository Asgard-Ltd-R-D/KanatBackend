namespace PacketProcessing.Config;

using Serilog;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.AspNetCore.Hosting;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Services.Networking;
using PacketProcessing.Services.Processing;
using System.Threading.Channels;

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

        
        // Register Channels for inter-service communication
        builder.Services.AddSingleton<Channel<MotionPacketEntity>>(sp =>
        {
            var config = sp.GetRequiredService<IConfiguration>();
            var maxMembers = config.GetValue<int>("DataPipes:MotionCapture:Channel:Members", 200000);
            return Channel.CreateBounded<MotionPacketEntity>(new BoundedChannelOptions(maxMembers)
            {
                FullMode = BoundedChannelFullMode.Wait
            });
        });
        
        builder.Services.AddSingleton<Channel<SafetyPacketEntity>>(sp =>
        {
            var config = sp.GetRequiredService<IConfiguration>();
            var maxMembers = config.GetValue<int>("DataPipes:SafetyCapture:Channel:Members", 100000);
            return Channel.CreateBounded<SafetyPacketEntity>(new BoundedChannelOptions(maxMembers)
            {
                FullMode = BoundedChannelFullMode.Wait
            });
        });
        
        builder.Services.AddSingleton<Channel<OnVIFPacketEntity>>(sp =>
        {
            var config = sp.GetRequiredService<IConfiguration>();
            var maxMembers = config.GetValue<int>("DataPipes:OnVIFCapture:Channel:Members", 1000);
            return Channel.CreateBounded<OnVIFPacketEntity>(new BoundedChannelOptions(maxMembers)
            {
                FullMode = BoundedChannelFullMode.Wait
            });
        });
        
        // Register Background Services
        // Capture Services (capture packets and write to channels)
        builder.Services.AddHostedService<MotionCaptureService>();
        builder.Services.AddHostedService<SafetyCaptureService>();
        builder.Services.AddHostedService<OnVIFCaptureService>();
        
        // Register Packet Processing Services as regular services (not background services)
        builder.Services.AddScoped<MotionPacketService>();
        builder.Services.AddScoped<SafetyPacketService>();
        builder.Services.AddScoped<OnVIFPacketService>();
        
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