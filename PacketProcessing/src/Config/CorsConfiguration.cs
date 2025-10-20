using System.Text.RegularExpressions;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.AspNetCore.Builder;

namespace PacketProcessing.Config;

/// <summary>
/// Cross-Origin Resource Sharing (CORS) Configuration Manager
/// 
/// Configures CORS policies for local IP addresses and localhost access only.
/// Allows controlled cross-origin requests from local network and development environments.
/// </summary>
public class CorsConfiguration
{
    /// <summary>
    /// The name of the CORS policy for local network and localhost origins
    /// </summary>
    private const string AllowLocalNetworkOrigins = "_allowLocalNetworkOrigins";
    
    /// <summary>
    /// Localhost patterns for development
    /// </summary>
    private static readonly string[] LocalhostPatterns = [
        @"^https?://localhost:\d+$",
        @"^https?://127\.0\.0\.1:\d+$",
        @"^https?://localhost:\d+/.*$",
        @"^https?://127\.0\.0\.1:\d+/.*$",
    ];
    
    /// <summary>
    /// LAN address patterns for local network access
    /// </summary>
    private static readonly string[] LanAddressPatterns = [
        // Private IP ranges (RFC 1918)
        @"^https?://10\.(?:[0-9]{1,3}\.){2}[0-9]{1,3}:\d+$", // 10.0.0.0/8
        @"^https?://10\.(?:[0-9]{1,3}\.){2}[0-9]{1,3}/.*$",
        @"^https?://10\.(?:[0-9]{1,3}\.){2}[0-9]{1,3}$",
        
        @"^https?://172\.(?:1[6-9]|2[0-9]|3[0-1])\.(?:[0-9]{1,3}\.)[0-9]{1,3}:\d+$", // 172.16.0.0/12
        @"^https?://172\.(?:1[6-9]|2[0-9]|3[0-1])\.(?:[0-9]{1,3}\.)[0-9]{1,3}/.*$",
        @"^https?://172\.(?:1[6-9]|2[0-9]|3[0-1])\.(?:[0-9]{1,3}\.)[0-9]{1,3}$",
        
        @"^https?://192\.168\.(?:[0-9]{1,3}\.)[0-9]{1,3}:\d+$", // 192.168.0.0/16
        @"^https?://192\.168\.(?:[0-9]{1,3}\.)[0-9]{1,3}/.*$",
        @"^https?://192\.168\.(?:[0-9]{1,3}\.)[0-9]{1,3}$",
        
        // Link-local addresses (RFC 3927)
        @"^https?://169\.254\.(?:[0-9]{1,3}\.)[0-9]{1,3}:\d+$", // 169.254.0.0/16
        @"^https?://169\.254\.(?:[0-9]{1,3}\.)[0-9]{1,3}/.*$",
        @"^https?://169\.254\.(?:[0-9]{1,3}\.)[0-9]{1,3}$",
    ];
    
    /// <summary>
    /// Checks if an origin is allowed based on local network addresses and localhost patterns
    /// </summary>
    /// <param name="origin">The origin to check</param>
    /// <returns>True if the origin is allowed, false otherwise</returns>
    private static bool IsAllowedOrigin(string origin)
    {
        // Check localhost patterns
        if (LocalhostPatterns.Any(pattern => Regex.IsMatch(origin, pattern)))
        {
            return true;
        }
        
        // Check LAN address patterns
        if (LanAddressPatterns.Any(pattern => Regex.IsMatch(origin, pattern)))
        {
            return true;
        }
        
        return false;
    }
    
    /// <summary>
    /// Configures CORS services and policies
    /// </summary>
    /// <param name="services">The service collection for CORS configuration</param>
    public static void ConfigureCorsServices(IServiceCollection services)
    {
        services.AddCors(options =>
        {
            options.AddPolicy(name: AllowLocalNetworkOrigins,
                policy =>
                {
                    policy.SetIsOriginAllowed(IsAllowedOrigin)
                        .AllowAnyMethod()
                        .AllowAnyHeader()
                        .AllowCredentials() // Required if using authentication
                        .SetIsOriginAllowedToAllowWildcardSubdomains(); // Allows subdomains
                });
        });
    }
    
    /// <summary>
    /// Configures CORS middleware in the application pipeline
    /// </summary>
    /// <param name="app">The WebApplication instance</param>
    public static void ConfigureCorsMiddleware(WebApplication app)
    {
        app.UseCors(AllowLocalNetworkOrigins);
    }
}