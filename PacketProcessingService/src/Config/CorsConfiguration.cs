using System.Text.RegularExpressions;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.AspNetCore.Builder;

namespace PacketProcessing.Config;

/// <summary>
/// Cross-Origin Resource Sharing (CORS) Configuration Manager
/// 
/// Restricts CORS strictly to localhost, LAN IP addresses, and 132.x.x.x internal IPs only.
/// </summary>
public static class CorsConfiguration
{
    /// <summary>
    /// The name of the CORS policy for local network and localhost origins
    /// </summary>
    private const string AllowLocalNetworkOrigins = "_allowLocalNetworkOrigins";
    
    /// <summary>
    /// Localhost patterns for development
    /// </summary>
    private static readonly string[] LocalhostPatterns = [
        @"^https?://localhost(:\d+)?/?$",
        @"^https?://127\.0\.0\.1(:\d+)?/?$"
    ];

    // --- Allow private LAN IP ranges (RFC1918 + link-local + 132.x internal) ---
    private static readonly string[] LanAddressPatterns = [
        // Private IP ranges
        @"^https?://10\.(?:[0-9]{1,3}\.){2}[0-9]{1,3}(:\d+)?/?$",                      // 10.0.0.0/8
        @"^https?://172\.(?:1[6-9]|2[0-9]|3[0-1])\.(?:[0-9]{1,3}\.)[0-9]{1,3}(:\d+)?/?$", // 172.16.0.0/12
        @"^https?://192\.168\.(?:[0-9]{1,3}\.)[0-9]{1,3}(:\d+)?/?$",                  // 192.168.0.0/16
        @"^https?://169\.254\.(?:[0-9]{1,3}\.)[0-9]{1,3}(:\d+)?/?$",                  // 169.254.0.0/16

        // Internal organizational range (e.g. 132.x.x.x)
        @"^https?://132\.(?:[0-9]{1,3}\.){2}[0-9]{1,3}(:\d+)?/?$"                     // 132.0.0.0/8
    ];

    /// <summary>
    /// Validates whether the incoming origin matches LAN, localhost, or internal 132.x.x.x.
    /// </summary>
    private static bool IsAllowedOrigin(string origin)
    {
        if (string.IsNullOrWhiteSpace(origin))
            return false;

        return LocalhostPatterns.Concat(LanAddressPatterns)
            .Any(pattern => Regex.IsMatch(origin, pattern, RegexOptions.IgnoreCase));
    }

    /// <summary>
    /// Register CORS policy restricted to localhost, LAN, and internal 132.x.x.x IPs.
    /// </summary>
    public static void ConfigureCorsServices(IServiceCollection services)
    {
        services.AddCors(options =>
        {
            options.AddPolicy(name: AllowLocalNetworkOrigins, policy =>
            {
                policy.SetIsOriginAllowed(IsAllowedOrigin)
                      .AllowAnyHeader()
                      .AllowAnyMethod()
                      .AllowCredentials(); // allow auth cookies/tokens if needed
            });
        });
    }

    /// <summary>
    /// Apply the CORS policy to the app.
    /// </summary>
    public static void ConfigureCorsMiddleware(WebApplication app)
    {
        app.UseCors(AllowLocalNetworkOrigins);
    }
}
