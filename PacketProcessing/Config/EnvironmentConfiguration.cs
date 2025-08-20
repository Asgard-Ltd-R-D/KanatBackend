using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Configuration;

namespace PacketProcessing.Config;

public class EnvironmentConfiguration
{
    public static void LoadConfigurations(WebApplicationBuilder builder)
    {
        builder.Configuration
            .SetBasePath(AppContext.BaseDirectory)
            .AddJsonFile("appsettings.json", optional: false, reloadOnChange: true)
            .AddJsonFile($"appsettings.{builder.Environment.EnvironmentName}.json", optional: true, reloadOnChange: true)
            .AddEnvironmentVariables();

        var appUrl = builder.Configuration.GetValue<string>("Application:Url");
        if (!string.IsNullOrEmpty(appUrl))
        {
            builder.WebHost.UseUrls(appUrl);
        }
    }
}