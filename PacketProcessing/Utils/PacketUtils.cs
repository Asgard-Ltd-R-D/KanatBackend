using SharpPcap;
using PacketDotNet;

namespace PacketProcessing.Utils;

public static class PacketUtils {
    public static (ulong timestamp, string sourceIp, string destinationIp, int sourcePort, int destinationPort, int length, string protocol)? ExtractPacketInfo(PacketCapture e) {
        var raw = e.GetPacket();
        if (raw == null) return null;

        // Let PacketDotNet parse based on the actual link-layer type (Ethernet, Linux SLL, etc.)
        var packet = Packet.ParsePacket(raw.LinkLayerType, raw.Data);

        // IPv4/IPv6
        var ipv4 = packet.Extract<IPv4Packet>();
        var ipv6 = ipv4 == null ? packet.Extract<IPv6Packet>() : null;

        if (ipv4 == null && ipv6 == null)
            return null;

        string srcIp, dstIp, proto = "unknown";
        int srcPort = 0, dstPort = 0;

        if (ipv4 != null) // IPv4
        {
            srcIp = ipv4.SourceAddress.ToString();
            dstIp = ipv4.DestinationAddress.ToString();

            var udp = packet.Extract<UdpPacket>();
            if (udp != null) { srcPort = udp.SourcePort; dstPort = udp.DestinationPort; proto = "udp"; }
            else
            {
                var tcp = packet.Extract<TcpPacket>();
                if (tcp != null) { srcPort = tcp.SourcePort; dstPort = tcp.DestinationPort; proto = "tcp"; }
                else proto = ipv4.Protocol.ToString().ToLowerInvariant();
            }
        }
        
        else // IPv6
        {
            srcIp = ipv6!.SourceAddress.ToString();
            dstIp = ipv6.DestinationAddress.ToString();

            var udp = packet.Extract<UdpPacket>();
            if (udp != null) { srcPort = udp.SourcePort; dstPort = udp.DestinationPort; proto = "udp"; }
            else
            {
                var tcp = packet.Extract<TcpPacket>();
                if (tcp != null) { srcPort = tcp.SourcePort; dstPort = tcp.DestinationPort; proto = "tcp"; }
                else proto = ipv6.NextHeader.ToString().ToLowerInvariant();
            }
        }

        int length = raw.Data.Length;
        ulong timestamp = raw.Timeval.MicroSeconds;

        return (timestamp, srcIp, dstIp, srcPort, dstPort, length, proto);
    }
}