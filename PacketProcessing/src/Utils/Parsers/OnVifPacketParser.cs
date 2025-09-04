using PacketProcessing.Entities.Packet;
using System.Buffers.Binary;
using System.Collections.Concurrent;
using System.Text;
using System.Xml.Linq;

namespace PacketProcessing.Utils.Parsers;

/// <summary>
/// Parser for OnVIF packets using HTTP/SOAP protocol
/// </summary>
public static class OnVifPacketParser
{
    private readonly struct XmlNs
    {
        public readonly XNamespace s, sa, soap, a, wsa, wsa5, tptz, tt, sdcs, empty;
        public XmlNs(XDocument doc)
        {
            var r = doc.Root!;
            s    = r.GetNamespaceOfPrefix("s")        ?? "http://schemas.xmlsoap.org/soap/envelope/";
            sa   = r.GetNamespaceOfPrefix("SOAP-ENV") ?? "http://schemas.xmlsoap.org/soap/envelope/";
            soap = "http://schemas.xmlsoap.org/soap/envelope/";
            a    = r.GetNamespaceOfPrefix("a")        ?? "http://www.w3.org/2005/08/addressing";
            wsa  = r.GetNamespaceOfPrefix("wsa")      ?? "http://schemas.xmlsoap.org/ws/2004/08/addressing";
            wsa5 = r.GetNamespaceOfPrefix("wsa5")     ?? "http://www.w3.org/2005/08/addressing";
            tptz = r.GetNamespaceOfPrefix("tptz")     ?? "http://www.onvif.org/ver20/ptz/wsdl";
            tt   = r.GetNamespaceOfPrefix("tt")       ?? "http://www.onvif.org/ver10/schema";
            sdcs = r.GetNamespaceOfPrefix("sdcs")     ?? "urn:schemas-xmlsoap-org:sdcs";
            empty = XNamespace.None;
        }
    }

    // Removed device IP dependency; we infer CMD/RPT heuristically now

    // CMD/RPT description map like in TS
    private static readonly IReadOnlyDictionary<string, (string CMD, string RPT)> DESCRIPTION_MAP =
        new Dictionary<string, (string, string)>(StringComparer.OrdinalIgnoreCase)
        {
            ["DAY"] = ("FOV_REQ", "FOV_STS"),
            ["IR"]  = ("FOV_REQ", "FOV_STS"),
            ["LRF"] = ("LRF_REQ", "LRF_STS"),
        };

    // Tracks messageId -> profile (DAY/IR/LRF) from the CMD so we can match the RPT
    private static readonly ConcurrentDictionary<string, string> _messageIdProfile = new(StringComparer.OrdinalIgnoreCase);

    /// <summary>
    /// Parses raw packet data into an OnVIFPacketEntity
    /// </summary>
    /// <param name="rawPacket">Raw packet bytes</param>
    /// <returns>Parsed OnVIFPacketEntity or null if parsing fails</returns>
    public static OnVIFPacketEntity? Parse(ReadOnlySpan<byte> rawPacket)
    {
        // Parse packet without debug output
        
        // ---- Try to extract HTTP from TCP packets first ----
        if (rawPacket.Length >= 54) // Minimum Ethernet + IP + TCP header
        {
            // Check if this looks like an Ethernet frame (starts with MAC addresses)
            if (rawPacket.Length >= 14 && rawPacket[12] == 0x08 && rawPacket[13] == 0x00) // IPv4
            {
                // Parse Ethernet header (14 bytes)
                var ipStartTcp = 14;
                
                // Parse IP header
                var ipHeaderLengthTcp = (rawPacket[ipStartTcp] & 0x0F) * 4; // IHL field
                var tcpStartTcp = ipStartTcp + ipHeaderLengthTcp;
                
                if (tcpStartTcp + 20 <= rawPacket.Length) // Minimum TCP header
                {
                    // Parse TCP header
                    var tcpHeaderLengthTcp = ((rawPacket[tcpStartTcp + 12] >> 4) & 0x0F) * 4; // Data offset field
                    var httpStartTcp = tcpStartTcp + tcpHeaderLengthTcp;
                    
                    if (httpStartTcp < rawPacket.Length)
                    {
                        var httpPayloadTcp = rawPacket[httpStartTcp..];
                        int httpHeaderEndTcp = IndexOf(httpPayloadTcp, "\r\n\r\n"u8);
                        
                        // Try to parse HTTP headers if found
                        if (httpHeaderEndTcp >= 0)
                        {
                            var bodyBytesTcp = httpPayloadTcp[(httpHeaderEndTcp + 4)..];
                            
                            // Interpret first 8 bytes as [float zoom][float measurement] if available
                            float? zoomFTcp = null;
                            float? measurementFTcp = null;
                            if (bodyBytesTcp.Length >= 4)
                            {
                                zoomFTcp = BitConverter.ToSingle(bodyBytesTcp[..4]);
                            }
                            if (bodyBytesTcp.Length >= 8)
                            {
                                measurementFTcp = BitConverter.ToSingle(bodyBytesTcp[4..8]);
                            }
                            
                            if (zoomFTcp.HasValue || measurementFTcp.HasValue)
                            {
                                return new OnVIFPacketEntity
                                {
                                    Id = Guid.NewGuid(),
                                    Timestamp = DateTime.UtcNow,
                                    Type = true, // Default for HTTP requests
                                    Description = "HTTP Request",
                                    Measurement = measurementFTcp ?? 0.0f,
                                    Zoom = zoomFTcp ?? 0.0f
                                };
                            }
                        }
                        else
                        {
                            // No HTTP headers found, but we have HTTP payload - create entity anyway
                            // This handles encrypted/compressed HTTP or other HTTP-like protocols
                            
                            // Use first 8 bytes as zoom/measurement if available
                            float? zoomFTcp = null;
                            float? measurementFTcp = null;
                            if (httpPayloadTcp.Length >= 4)
                            {
                                zoomFTcp = BitConverter.ToSingle(httpPayloadTcp[..4]);
                            }
                            if (httpPayloadTcp.Length >= 8)
                            {
                                measurementFTcp = BitConverter.ToSingle(httpPayloadTcp[4..8]);
                            }
                            
                            return new OnVIFPacketEntity
                            {
                                Id = Guid.NewGuid(),
                                Timestamp = DateTime.UtcNow,
                                Type = true, // Default for HTTP requests
                                Description = "HTTP Payload (Encrypted/Compressed)",
                                Measurement = measurementFTcp ?? 0.0f,
                                Zoom = zoomFTcp ?? 0.0f
                            };
                        }
                    }
                }
            }
        }
        
        // ---- Fallback: HTTP present anywhere in the payload (works with loopback/Ethernet frames) ----
        if (rawPacket.Length >= 8)
        {
            int httpHeaderEnd = IndexOf(rawPacket, "\r\n\r\n"u8);
            // Debug output removed
            if (httpHeaderEnd >= 0)
            {
                var bodyBytesFallback = rawPacket[(httpHeaderEnd + 4)..];

                // Interpret first 8 bytes as [float zoom][float measurement] if available
                float? zoomF = null;
                float? measurementF = null;
                if (bodyBytesFallback.Length >= 4)
                {
                    zoomF = BitConverter.ToSingle(bodyBytesFallback[..4]);
                }
                if (bodyBytesFallback.Length >= 8)
                {
                    measurementF = BitConverter.ToSingle(bodyBytesFallback.Slice(4, 4));
                }

                return new OnVIFPacketEntity
                {
                    Id = Guid.NewGuid(),
                    Timestamp = DateTime.UtcNow,
                    Type = true,
                    Description = "UNKNOWN",
                    Zoom = zoomF,
                    Measurement = measurementF ?? 0f
                };
            }
        }

        // -------- Ethernet --------
        if (rawPacket.Length < 14) return null;
        int offset;
        ushort ethType = ReadBE16(rawPacket.Slice(12, 2));
        offset = 14;

        // VLAN/QinQ
        if (ethType == 0x8100 || ethType == 0x88A8)
        {
            if (rawPacket.Length < offset + 4) return null;
            ethType = ReadBE16(rawPacket.Slice(offset + 2, 2));
            offset += 4;
        }

        // -------- IPv4 only --------
        if (ethType != 0x0800) return null;
        if (rawPacket.Length < offset + 20) return null;

        int ipStart = offset;
        byte verIhl = rawPacket[ipStart];
        if ((verIhl >> 4) != 4) return null;
        int ihlBytes = (verIhl & 0x0F) * 4;
        if (ihlBytes < 20) return null;
        if (rawPacket.Length < ipStart + ihlBytes) return null;

        byte proto = rawPacket[ipStart + 9];
        if (proto != 6) return null; // TCP only

        // IPs not needed for current heuristics

        // -------- TCP --------
        int tcpStart = ipStart + ihlBytes;
        if (rawPacket.Length < tcpStart + 20) return null;

        ushort srcPort = ReadBE16(rawPacket.Slice(tcpStart + 0, 2));

        byte dataOffsetFlags = rawPacket[tcpStart + 12];
        int tcpHdrLen = ((dataOffsetFlags >> 4) & 0x0F) * 4;
        if (tcpHdrLen < 20) return null;
        if (rawPacket.Length < tcpStart + tcpHdrLen) return null;

        int appStart = tcpStart + tcpHdrLen;
        if (appStart >= rawPacket.Length) return null;
        ReadOnlySpan<byte> http = rawPacket[appStart..];

        // -------- HTTP --------
        // Find header/body split: \r\n\r\n
        int headerEnd = IndexOf(http, "\r\n\r\n"u8);
        if (headerEnd < 0) return null; // not a complete HTTP message in this frame
        var headerBytes = http.Slice(0, headerEnd);
        var bodyBytes = http.Slice(headerEnd + 4);

        // Parse headers into dictionary
        var headers = ParseHttpHeaders(headerBytes);
        bool isChunked = headers.TryGetValue("transfer-encoding", out var te) && te.Contains("chunked", StringComparison.OrdinalIgnoreCase);
        int contentLength = headers.TryGetValue("content-length", out var cl) && int.TryParse(cl, out var len) ? len : -1;

        byte[] bodyBuf;
        if (isChunked)
        {
            if (!TryDechunk(bodyBytes, out bodyBuf)) return null;
        }
        else
        {
            if (contentLength >= 0)
            {
                if (bodyBytes.Length < contentLength) return null;
                bodyBuf = bodyBytes[..contentLength].ToArray();
            }
            else
            {
                // No CL, assume rest of segment is body
                bodyBuf = bodyBytes.ToArray();
            }
        }

        // If body is binary (no XML), support 8-byte fallback: [float zoom][float measurement]
        if (bodyBuf.Length >= 8 && Array.IndexOf(bodyBuf, (byte)'<') < 0)
        {
            var zoomF = BitConverter.ToSingle(bodyBuf.AsSpan(0, 4));
            var measurementF = BitConverter.ToSingle(bodyBuf.AsSpan(4, 4));
            return new OnVIFPacketEntity
            {
                Id = Guid.NewGuid(),
                Timestamp = DateTime.UtcNow,
                Type = true,
                Description = "UNKNOWN",
                Zoom = zoomF,
                Measurement = measurementF
            };
        }

        // Convert to string (remove NULs, trim)
        string body = Encoding.UTF8.GetString(bodyBuf).Replace("\0", string.Empty).Trim();
        int xmlStart = body.IndexOf('<');
        if (xmlStart < 0) return null;
        string xml = body[xmlStart..].Trim();

        // Quick completeness check for SOAP Envelope markers (not foolproof)
        if (!LooksLikeCompleteSoap(xml)) return null;

        // -------- SOAP/XML --------
        XDocument doc;
        try { doc = XDocument.Parse(xml, LoadOptions.None); }
        catch { return null; }

        var ns = new XmlNs(doc);

        // Header/Body nodes
        var env = doc.Root;
        if (env is null) return null;
        var header = env.Element(ns.s + "Header") ?? env.Element(ns.sa + "Header") ?? env.Element(ns.soap + "Header");
        var bodyEl = env.Element(ns.s + "Body") ?? env.Element(ns.sa + "Body") ?? env.Element(ns.soap + "Body");
        if (header is null || bodyEl is null) return null;

        // MessageID
        var msgIdVal = header.Element(ns.a + "MessageID")?.Value
                    ?? header.Element(ns.wsa5 + "MessageID")?.Value
                    ?? header.Element(ns.wsa + "MessageID")?.Value;
        if (string.IsNullOrWhiteSpace(msgIdVal)) return null;
        string cleanMsgId = ExtractUuid(msgIdVal); // urn:uuid:<uuid> -> <uuid>

        // Determine CMD vs RPT heuristically (no device IP required)
        // - If WS-Addressing Action or SOAPAction contains "Response" → RPT
        // - If SOAP Body contains any element whose local name ends with "Response" → RPT
        // - As an additional hint, packets from server-side ports (80/8080) tend to be RPT
        string actionHeader = headers.TryGetValue("action", out var actionVal)
            ? actionVal
            : (headers.TryGetValue("soapaction", out var soapActionVal) ? soapActionVal : string.Empty);
        bool actionLooksLikeResponse = !string.IsNullOrEmpty(actionHeader) && actionHeader.Contains("Response", StringComparison.OrdinalIgnoreCase);
        bool bodyLooksLikeResponse = bodyEl.Descendants().Any(e => e.Name.LocalName.EndsWith("Response", StringComparison.OrdinalIgnoreCase));
        bool srcLooksLikeServer = srcPort is 80 or 8080;

        string type = (actionLooksLikeResponse || bodyLooksLikeResponse || srcLooksLikeServer) ? "RPT" : "CMD";

        string profile = "UNKNOWN";
        string description = "UNKNOWN";
        float? zoom = null;
        float? measurement = null;

        if (type == "CMD")
        {
            // Heuristics to infer profile from CMD
            var getStatus = bodyEl.Element(ns.tptz + "GetStatus");
            var profileToken = getStatus?.Element(ns.tptz + "ProfileToken")?.Value
                            ?? getStatus?.Element("ProfileToken")?.Value;
            if (string.Equals(profileToken, "day", StringComparison.OrdinalIgnoreCase)) profile = "DAY";
            else if (string.Equals(profileToken, "night_combined", StringComparison.OrdinalIgnoreCase)) profile = "IR";
            else if (BodyContains(bodyEl, ns.sdcs + "GetPower") || BodyContains(bodyEl, "GetPower"))
                profile = "LRF";

            description = DESCRIPTION_MAP.TryGetValue(profile, out var pair) ? pair.CMD : "UNKNOWN";

            // Remember mapping for RPT
            if (!string.IsNullOrEmpty(cleanMsgId))
                _messageIdProfile[cleanMsgId] = profile;
        }
        else
        {
            // RPT: use previous CMD mapping; fallback by content
            if (!string.IsNullOrEmpty(cleanMsgId) && _messageIdProfile.TryRemove(cleanMsgId, out var mappedProfile))
            {
                profile = mappedProfile;
            }
            else
            {
                // Fallback: if it looks like an LRF measurement response
                if (BodyContains(bodyEl, ns.sdcs + "LRFMakeMeasurementResponse"))
                    profile = "LRF";
            }

            description = DESCRIPTION_MAP.TryGetValue(profile, out var pair) ? pair.RPT : "UNKNOWN";

            // Extract zoom for DAY/IR: tptz:GetStatusResponse/tptz:PTZStatus/tt:Position/tt:Zoom @x
            if (profile is "DAY" or "IR")
            {
                var getStatusResp = bodyEl.Element(ns.tptz + "GetStatusResponse");
                var ptzStatus = getStatusResp?.Element(ns.tptz + "PTZStatus") ?? getStatusResp?.Element("PTZStatus");
                var position = ptzStatus?.Element(ns.tt + "Position") ?? ptzStatus?.Element("Position");
                var zoomEl = position?.Element(ns.tt + "Zoom") ?? position?.Element("Zoom");

                string? xAttr = zoomEl?.Attribute("x")?.Value ?? zoomEl?.Attribute(ns.empty + "x")?.Value;
                if (xAttr != null && float.TryParse(xAttr, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var z))
                    zoom = (float)Math.Round(z, 3);
            }

            // Extract LRF measurement
            if (profile == "LRF")
            {
                var lrfResp = FindFirst(bodyEl, ns.sdcs + "LRFMakeMeasurementResponse") ?? FindFirst(bodyEl, "LRFMakeMeasurementResponse");
                var measVal = lrfResp?.Element("Measurement")?.Value ?? lrfResp?.Element(ns.empty + "Measurement")?.Value;
                if (measVal != null)
                {
                    measurement = measVal == "[Error: 1001]" ? -1000f
                        : (float?)Math.Round(ParseInvariantFloat(measVal), 3);
                }
            }
        }

        // ---- Build entity (adjust to your exact model) ----
        return new OnVIFPacketEntity
        {
            Id = Guid.NewGuid(),
            Timestamp = DateTime.UtcNow,          // if your entity uses ulong identity timestamp, remove this
            Type = type == "RPT",                 // you can reinterpret: true=RPT (device report), false=CMD
            Description = description,
            Zoom = zoom,
            Measurement = measurement ?? 0f       // or null if your model allows
        };
    }

    private static int IndexOf(ReadOnlySpan<byte> haystack, ReadOnlySpan<byte> needle)
    {
        // simple span search
        for (int i = 0; i <= haystack.Length - needle.Length; i++)
        {
            if (haystack.Slice(i, needle.Length).SequenceEqual(needle))
                return i;
        }
        return -1;
    }

    private static Dictionary<string, string> ParseHttpHeaders(ReadOnlySpan<byte> headerBytes)
    {
        var dict = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var s = Encoding.ASCII.GetString(headerBytes);
        var lines = s.Split("\r\n", StringSplitOptions.RemoveEmptyEntries);
        // lines[0] is request/status line — we can ignore it
        for (int i = 1; i < lines.Length; i++)
        {
            int sep = lines[i].IndexOf(':');
            if (sep > 0)
            {
                string name = lines[i].Substring(0, sep).Trim();
                string val = lines[i].Substring(sep + 1).Trim();
                dict[name] = val;
            }
        }
        return dict;
    }

    private static bool TryDechunk(ReadOnlySpan<byte> chunked, out byte[] body)
    {
        // minimal dechunker: size\r\n<data>\r\n ... 0\r\n\r\n
        var ms = new MemoryStream();
        int idx = 0;
        while (true)
        {
            int lineEnd = IndexOf(chunked[idx..], "\r\n"u8);
            if (lineEnd < 0) { body = Array.Empty<byte>(); return false; }
            int hexLenStart = idx;
            int hexLenEnd = idx + lineEnd;
            string hexStr = Encoding.ASCII.GetString(chunked.Slice(hexLenStart, lineEnd));
            if (!int.TryParse(hexStr.Split(';')[0], System.Globalization.NumberStyles.HexNumber, null, out int size))
            {
                body = Array.Empty<byte>(); return false;
            }
            idx = hexLenEnd + 2; // skip \r\n
            if (size == 0) break;
            if (chunked.Length < idx + size + 2) { body = Array.Empty<byte>(); return false; }
            ms.Write(chunked.Slice(idx, size));
            idx += size;
            // trailing \r\n
            if (chunked.Length < idx + 2 || chunked[idx] != (byte)'\r' || chunked[idx + 1] != (byte)'\n')
            {
                body = Array.Empty<byte>(); return false;
            }
            idx += 2;
        }
        // final CRLF after 0-size chunk (optional headers ignored)
        // try to consume optional "\r\n"
        body = ms.ToArray();
        return true;
    }

    private static bool LooksLikeCompleteSoap(string xml)
    {
        // quick checks for envelope balance
        bool hasS = xml.Contains("<s:Envelope", StringComparison.Ordinal) && xml.Contains("</s:Envelope>", StringComparison.Ordinal);
        bool hasSA = xml.Contains("<SOAP-ENV:Envelope", StringComparison.Ordinal) && xml.Contains("</SOAP-ENV:Envelope>", StringComparison.Ordinal);
        bool hasPlain = xml.Contains("<Envelope", StringComparison.Ordinal) && xml.Contains("</Envelope>", StringComparison.Ordinal);
        return hasS || hasSA || hasPlain;
    }

    private static string ExtractUuid(string messageId)
    {
        // urn:uuid:xxxxxxxx-... -> take the last part after final ':'
        int i = messageId.LastIndexOf(':');
        return i >= 0 ? messageId[(i + 1)..] : messageId;
    }

    private static bool BodyContains(XElement body, XName name)
        => body.Descendants(name).Any();

    private static bool BodyContains(XElement body, string localName)
        => body.Descendants().Any(e => string.Equals(e.Name.LocalName, localName, StringComparison.OrdinalIgnoreCase));

    private static XElement? FindFirst(XElement body, XName name)
        => body.Descendants(name).FirstOrDefault();

    private static float ParseInvariantFloat(string s)
        => float.Parse(s, System.Globalization.CultureInfo.InvariantCulture);

    private static ushort ReadBE16(ReadOnlySpan<byte> s) => 
        BinaryPrimitives.ReadUInt16BigEndian(s);

    private static string ToIPv4(ReadOnlySpan<byte> s) =>
        $"{s[0]}.{s[1]}.{s[2]}.{s[3]}";
}
