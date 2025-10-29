namespace PacketProcessing.Utils.Filters;

public static class BpfFilterBuilder
{
    /// <summary>
    /// Builds a BPF filter string based on the protocol and IPs.
    /// returns the filter constructed as {protocol} and (port {port number} or port {port number} or ...)
    /// </summary>
    /// <param name="protocol"></param>
    /// <param name="ips"></param>
    /// <returns></returns>
    public static string Build(string protocol, IEnumerable<string>? ports)
    {
        // Base: protocol
        var proto = protocol?.ToLowerInvariant() switch
        {
            "tcp" => "tcp",
            "udp" => "udp",
            "http" => "tcp port 80",
            "any" => string.Empty,
            _ => protocol ?? string.Empty
        };

        var conditions = new List<string>();
        if (!string.IsNullOrWhiteSpace(proto))
            conditions.Add(proto);

        if (ports is not null && ports.Any())
        {
            var portExprs = ports.Select(ip => $"port {ip}");
            conditions.Add($"({string.Join(" or ", portExprs)})");
        }

        return string.Join(" and ", conditions);
    }
}
