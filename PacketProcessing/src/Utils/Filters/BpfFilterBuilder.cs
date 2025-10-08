namespace PacketProcessing.Utils.Filters;

public static class BpfFilterBuilder
{
    /// <summary>
    /// Builds a BPF filter string based on the protocol and IPs.
    /// returns the filter constructed as {protocol} and (host {ip} or host {ip} or ...)
    /// </summary>
    /// <param name="protocol"></param>
    /// <param name="ips"></param>
    /// <returns></returns>
    public static string Build(string protocol, IEnumerable<string>? ips)
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

        if (ips is not null && ips.Any())
        {
            var ipExprs = ips.Select(ip => $"host {ip}");
            conditions.Add($"({string.Join(" or ", ipExprs)})");
        }

        conditions.Add("greater 0");

        return string.Join(" and ", conditions);
    }
}
