using Microsoft.Extensions.Configuration;
using PacketProcessing.DTOs.Conf;
using PacketProcessing.DTOs.Range;

namespace PacketProcessing.Utils.ModelValidator;

public static class RangeModelValidator
{

    /// <summary>
    /// Validate the provided RangeDto and hydrate missing configuration values from appsettings.json defaults.
    /// - Ensures Config exists
    /// - Ensures BPFConfDto exists and Device is in available device list
    /// - Fills EndpointSpecification arrays using DataPipes defaults where missing
    /// - Ensures MtxConfig exists (hydrate defaults if missing)
    /// - Ensures Cams exists (hydrate defaults if missing)
    /// Returns a possibly updated RangeDto; throws ArgumentException if validation fails
    /// </summary>
    public static RangeDto ValidateAndHydrate(
        RangeDto range,
        IEnumerable<string> availableDevices,
        IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(range);

        // Ensure Config
        if (range.Config is null)
        {
            throw new ArgumentException("Range.Config must be provided");
        }

        // Ensure BPFConfDto
        if (range.Config.BpfConfig is null)
        {
            throw new ArgumentException("Range.Config.BpfConfig must be provided");
        }

        // Validate Device exists in available device list
        var devices = availableDevices ?? [];
        if (string.IsNullOrWhiteSpace(range.Config.BpfConfig.Device) ||
            !devices.Contains(range.Config.BpfConfig.Device, StringComparer.OrdinalIgnoreCase))
        {
            throw new ArgumentException($"BpfConfig.Device must exist and be in available device list. Provided: '{range.Config.BpfConfig.Device ?? "<null>"}'");
        }

        // Fetch defaults from configuration for each DataPipe
        var motionIps = GetIps(configuration, "DataPipes:MotionCapture:Network:IPs");
        var safetyIps = GetIps(configuration, "DataPipes:SafetyCapture:Network:IPs");
        var onvifIps  = GetIps(configuration, "DataPipes:OnVIFCapture:Network:IPs");
        var motionPorts = GetPorts(configuration, "DataPipes:MotionCapture:Network:Ports");
        var safetyPorts = GetPorts(configuration, "DataPipes:SafetyCapture:Network:Ports");
        var onvifPorts = GetPorts(configuration, "DataPipes:OnVIFCapture:Network:Ports");

        // Endpoints: if provided is null/empty, hydrate from defaults; if provided exists, do NOT override missing fields
        range.Config.BpfConfig.Motion = HydrateEndpoints(range.Config.BpfConfig.Motion, motionIps, motionPorts);
        range.Config.BpfConfig.Safety = HydrateSafetyEndpoints(range.Config.BpfConfig.Safety, safetyIps, safetyPorts);
        range.Config.BpfConfig.OnVIF  = HydrateEndpoints(range.Config.BpfConfig.OnVIF,  onvifIps, onvifPorts);

        // Ensure MtxConfig (default from configuration)
        range.Config.MtxConfig = HydrateEndpoint(range.Config.MtxConfig, GetDefaultMtx(configuration));

        // Ensure Cams
        if (range.Config.Cams is null || range.Config.Cams.Length == 0)
        {
            // Try to fetch default cams from configuration: Application:DefaultCams:[{Alias,IsRecording}]
            var defaultCams = configuration.GetSection("Application:DefaultCams").Get<CameraConfDto[]>() ?? [];
            range.Config.Cams = (defaultCams.Length > 0)
                ? defaultCams
                : [ new CameraConfDto { Alias = "Default", IsRecording = false } ];
        }

        return range;
    }

    private static EndpointSpecification[] HydrateEndpoints(EndpointSpecification[]? provided, string[] defaultIps, int[] defaultPorts)
    {
        // If caller provided endpoints, return as-is (do NOT override missing ip/port)
        if (provided != null && provided.Length > 0)
            return provided;

        // Otherwise, build endpoints from defaults (if any). If no defaults, return empty
        if (defaultIps.Length == 0 && defaultPorts.Length == 0)
            return [];

        int length = Math.Max(defaultIps.Length, defaultPorts.Length);
        var result = new List<EndpointSpecification>(length);

        string? FirstIp() => defaultIps.Length > 0 ? defaultIps[0] : null;
        int? FirstPort() => defaultPorts.Length > 0 ? defaultPorts[0] : (int?)null;

        for (int i = 0; i < length; i++)
        {
            var defIp = i < defaultIps.Length ? defaultIps[i] : FirstIp();
            var defPort = i < defaultPorts.Length ? defaultPorts[i] : FirstPort();
            result.Add(new EndpointSpecification(defIp, defPort));
        }

        return [.. result];
    }

    private static BPFConfDto.SafetyConf HydrateSafetyEndpoints(BPFConfDto.SafetyConf? provided, string[] defaultIps, int[] defaultPorts)
    {
        // If caller provided anything for safety, return as-is (do NOT override missing Sbe/Pbe)
        if (provided is not null && (provided.Sbe is not null || provided.Pbe is not null))
        {
            return provided;
        }

        // Otherwise, build from defaults (if any). If no defaults, return nulls
        EndpointSpecification? BuildAt(int index)
        {
            string? ip = null;
            int? port = null;

            if (defaultIps.Length > 0)
            {
                ip = index < defaultIps.Length ? defaultIps[index] : defaultIps[0];
            }

            if (defaultPorts.Length > 0)
            {
                port = index < defaultPorts.Length ? defaultPorts[index] : defaultPorts[0];
            }

            if (string.IsNullOrWhiteSpace(ip) && port is null)
            {
                return null;
            }

            return new EndpointSpecification(ip, port);
        }

        var sbe = BuildAt(0);
        var pbe = BuildAt(1);

        return new BPFConfDto.SafetyConf
        {
            Sbe = sbe,
            Pbe = pbe
        };
    }

    private static EndpointSpecification HydrateEndpoint(EndpointSpecification? provided, EndpointSpecification @default)
    {
        if (provided is null)
        {
            return @default;
        }

        var ip = string.IsNullOrWhiteSpace(provided.Value.IP) ? @default.IP : provided.Value.IP;
        var port = provided.Value.Port ?? @default.Port;
        return new EndpointSpecification(ip, port);
    }

    private static string[] GetIps(IConfiguration configuration, string key)
    {
        var section = configuration.GetSection(key);
        if (!section.Exists()) return [];
        var ips = section.Get<string[]>() ?? [];
        return [.. ips.Where(ip => !string.IsNullOrWhiteSpace(ip))];
    }

    private static int[] GetPorts(IConfiguration configuration, string key)
    {
        var section = configuration.GetSection(key);
        if (!section.Exists()) return [];
        var ports = section.Get<int[]>() ?? [];
        return [.. ports.Where(port => port > 0)];
    }

    private static EndpointSpecification GetDefaultMtx(IConfiguration configuration)
    {
        var ip = configuration["MediaMtx:IP"] ?? configuration["Application:Mtx:IP"];
        int? port = null;
        var portStr = configuration["MediaMtx:Port"] ?? configuration["Application:Mtx:Port"];
        if (int.TryParse(portStr, out var parsed)) port = parsed;
        return new EndpointSpecification(ip, port);
    }
}


