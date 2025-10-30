using PacketProcessing.DTOs.Conf;

namespace PacketProcessing.Utils.Filters;

public static class BpfFilterBuilder
{
    /// <summary>
    /// Builds a BPF filter string based on the protocol and endpoint specifications (IP/Port pairs).
    /// - Protocol is converted to base expression (e.g., tcp/udp/http -> tcp port 80)
    /// - Endpoints provide IPs and/or Ports.
    /// - Construct two OR-groups: (host ip1 or host ip2 ...) and (port p1 or port p2 ...)
    /// - The final filter is: protocol and [ip-group?] and [port-group?]
    /// - If an OR-group has no values, it's omitted.
    /// </summary>
    public static string Build(string protocol, IEnumerable<EndpointSpecification>? endpoints)
    {
        var proto = protocol?.ToLowerInvariant() switch
        {
            "tcp" => "tcp",
            "udp" => "udp",
            "http" => "tcp port 80",
            "any" => string.Empty,
            _ => protocol ?? string.Empty
        };

        var clauses = new List<string>();
        if (!string.IsNullOrWhiteSpace(proto))
            clauses.Add(proto);

        if (endpoints is not null)
        {
            var ipExprs = new List<string>();
            var portExprs = new List<string>();
            foreach (var ep in endpoints)
            {
                if (!string.IsNullOrWhiteSpace(ep.IP)) ipExprs.Add($"host {ep.IP}");
                if (ep.Port.HasValue && ep.Port.Value > 0) portExprs.Add($"port {ep.Port.Value}");
            }

            if (ipExprs.Count > 0)
                clauses.Add($"({string.Join(" or ", ipExprs)})");
            if (portExprs.Count > 0)
                clauses.Add($"({string.Join(" or ", portExprs)})");
        }

        return string.Join(" and ", clauses);
    }

    /// <summary>
    /// Builds a BPF filter string based on the protocol and IPs.
    /// returns the filter constructed as {protocol} and (host {ip} or host {ip} or ...)
    /// </summary>
    /// <param name="protocol"></param>
    /// <param name="ips"></param>
    /// <returns></returns>
    [Obsolete("Use Build(string, IEnumerable<EndpointSpecification>) instead")]
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

        return string.Join(" and ", conditions);
    }
}
