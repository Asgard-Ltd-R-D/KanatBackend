using PacketProcessing.Entities.Packet;
using System.Buffers.Binary;
using System.Collections.Concurrent;
using System.Text;
using System.Xml.Linq;
using Microsoft.Extensions.Logging;

namespace PacketProcessing.Utils.Parsers;

/// <summary>
/// Parser for OnVIF packets using HTTP/SOAP protocol
/// </summary>
public static class OnVifPacketParser
{
    private static ILogger? _logger;
    
    public static void SetLogger(ILogger logger)
    {
        _logger = logger;
    }
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
        try
        {
            _logger?.LogDebug("Starting OnVIF packet parsing. Packet length: {Length} bytes", rawPacket.Length);
            _logger?.LogDebug("Raw packet data: {Data}", BitConverter.ToString(rawPacket.ToArray()).Replace("-", ""));
            
            // Parse packet without debug output
        
            // ---- Try to extract HTTP from TCP packets first ----
            if (rawPacket.Length >= 54) // Minimum Ethernet + IP + TCP header
            {
                _logger?.LogDebug("Attempting TCP/HTTP parsing for packet length: {Length}", rawPacket.Length);
                
                // Check if this looks like an Ethernet frame (starts with MAC addresses)
                if (rawPacket.Length >= 14 && rawPacket[12] == 0x08 && rawPacket[13] == 0x00) // IPv4
                {
                    _logger?.LogDebug("Detected IPv4 Ethernet frame");
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
                    
                    _logger?.LogDebug("TCP header parsed - Header length: {TcpHeaderLength}, HTTP start: {HttpStart}", tcpHeaderLengthTcp, httpStartTcp);
                    
                    if (httpStartTcp < rawPacket.Length)
                    {
                        var httpPayloadTcp = rawPacket[httpStartTcp..];
                        int httpHeaderEndTcp = IndexOf(httpPayloadTcp, "\r\n\r\n"u8);
                        
                        _logger?.LogDebug("HTTP payload extracted - Length: {PayloadLength}, Header end found: {HeaderEndFound}", 
                            httpPayloadTcp.Length, httpHeaderEndTcp >= 0);
                        
                        // Try to parse HTTP headers if found
                        if (httpHeaderEndTcp >= 0)
                        {
                            var bodyBytesTcp = httpPayloadTcp[(httpHeaderEndTcp + 4)..];
                            _logger?.LogDebug("HTTP headers found, body length: {BodyLength}", bodyBytesTcp.Length);
                            
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
                                _logger?.LogDebug("Successfully parsed HTTP request with zoom: {Zoom}, measurement: {Measurement}", zoomFTcp, measurementFTcp);
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
                            else
                            {
                                _logger?.LogWarning("HTTP request body found but no valid zoom/measurement data extracted. Body length: {BodyLength}", bodyBytesTcp.Length);
                            }
                        }
                        else
                        {
                            _logger?.LogDebug("No HTTP headers found, treating as encrypted/compressed HTTP payload");
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
                            
                            _logger?.LogDebug("Successfully parsed encrypted/compressed HTTP payload with zoom: {Zoom}, measurement: {Measurement}", zoomFTcp, measurementFTcp);
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
                    else
                    {
                        _logger?.LogWarning("TCP packet too short for HTTP parsing. Required: {Required}, Available: {Available}", 
                            tcpStartTcp + 20, rawPacket.Length);
                    }
                }
                else
                {
                    _logger?.LogWarning("Invalid IP header length. IHL: {Ihl}, Packet length: {Length}", 
                        (rawPacket[ipStartTcp] & 0x0F) * 4, rawPacket.Length);
                }
            }
            else
            {
                _logger?.LogWarning("Packet too short for Ethernet frame parsing. Required: 14 bytes, Available: {Length}", rawPacket.Length);
            }
        }
        else
        {
            _logger?.LogWarning("Packet too short for TCP/HTTP parsing. Required: 54 bytes, Available: {Length}", rawPacket.Length);
        }
        
        // ---- Fallback: HTTP present anywhere in the payload (works with loopback/Ethernet frames) ----
        if (rawPacket.Length >= 8)
        {
            _logger?.LogDebug("Attempting fallback HTTP parsing for packet length: {Length}", rawPacket.Length);
            int httpHeaderEnd = IndexOf(rawPacket, "\r\n\r\n"u8);
            if (httpHeaderEnd >= 0)
            {
                _logger?.LogDebug("Fallback HTTP headers found at position: {HeaderEnd}", httpHeaderEnd);
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

                _logger?.LogDebug("Fallback HTTP parsing successful - zoom: {Zoom}, measurement: {Measurement}", zoomF, measurementF);
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
            else
            {
                _logger?.LogDebug("No HTTP headers found in fallback parsing");
            }
        }

        // -------- Ethernet --------
        if (rawPacket.Length < 14) 
        {
            _logger?.LogWarning("Packet too short for Ethernet parsing. Required: 14 bytes, Available: {Length}", rawPacket.Length);
            return null;
        }
        int offset;
        ushort ethType = ReadBE16(rawPacket.Slice(12, 2));
        offset = 14;
        _logger?.LogDebug("Ethernet frame detected - EtherType: 0x{EthType:X4}", ethType);

        // VLAN/QinQ
        if (ethType == 0x8100 || ethType == 0x88A8)
        {
            _logger?.LogDebug("VLAN/QinQ tag detected - EtherType: 0x{EthType:X4}", ethType);
            if (rawPacket.Length < offset + 4) 
            {
                _logger?.LogWarning("Packet too short for VLAN tag parsing. Required: {Required}, Available: {Available}", offset + 4, rawPacket.Length);
                return null;
            }
            ethType = ReadBE16(rawPacket.Slice(offset + 2, 2));
            offset += 4;
            _logger?.LogDebug("Inner EtherType after VLAN: 0x{EthType:X4}", ethType);
        }

        // -------- IPv4 only --------
        if (ethType != 0x0800) 
        {
            _logger?.LogWarning("Non-IPv4 EtherType detected: 0x{EthType:X4}. Only IPv4 is supported.", ethType);
            return null;
        }
        if (rawPacket.Length < offset + 20) 
        {
            _logger?.LogWarning("Packet too short for IPv4 header. Required: {Required}, Available: {Available}", offset + 20, rawPacket.Length);
            return null;
        }
        _logger?.LogDebug("IPv4 packet detected");

        int ipStart = offset;
        byte verIhl = rawPacket[ipStart];
        if ((verIhl >> 4) != 4) 
        {
            _logger?.LogWarning("Invalid IP version: {Version}. Only IPv4 is supported.", verIhl >> 4);
            return null;
        }
        int ihlBytes = (verIhl & 0x0F) * 4;
        if (ihlBytes < 20) 
        {
            _logger?.LogWarning("Invalid IP header length: {Ihl} bytes. Minimum is 20 bytes.", ihlBytes);
            return null;
        }
        if (rawPacket.Length < ipStart + ihlBytes) 
        {
            _logger?.LogWarning("Packet too short for IP header. Required: {Required}, Available: {Available}", ipStart + ihlBytes, rawPacket.Length);
            return null;
        }

        byte proto = rawPacket[ipStart + 9];
        if (proto != 6) 
        {
            _logger?.LogWarning("Non-TCP protocol detected: {Protocol}. Only TCP is supported.", proto);
            return null;
        }
        _logger?.LogDebug("TCP protocol confirmed");

        // IPs not needed for current heuristics

        // -------- TCP --------
        int tcpStart = ipStart + ihlBytes;
        if (rawPacket.Length < tcpStart + 20) 
        {
            _logger?.LogWarning("Packet too short for TCP header. Required: {Required}, Available: {Available}", tcpStart + 20, rawPacket.Length);
            return null;
        }

        ushort srcPort = ReadBE16(rawPacket.Slice(tcpStart + 0, 2));
        _logger?.LogDebug("TCP source port: {SrcPort}", srcPort);

        byte dataOffsetFlags = rawPacket[tcpStart + 12];
        int tcpHdrLen = ((dataOffsetFlags >> 4) & 0x0F) * 4;
        if (tcpHdrLen < 20) 
        {
            _logger?.LogWarning("Invalid TCP header length: {TcpHdrLen} bytes. Minimum is 20 bytes.", tcpHdrLen);
            return null;
        }
        if (rawPacket.Length < tcpStart + tcpHdrLen) 
        {
            _logger?.LogWarning("Packet too short for complete TCP header. Required: {Required}, Available: {Available}", tcpStart + tcpHdrLen, rawPacket.Length);
            return null;
        }

        int appStart = tcpStart + tcpHdrLen;
        if (appStart >= rawPacket.Length) 
        {
            _logger?.LogWarning("No application data after TCP header. App start: {AppStart}, Packet length: {Length}", appStart, rawPacket.Length);
            return null;
        }
        ReadOnlySpan<byte> http = rawPacket[appStart..];
        _logger?.LogDebug("HTTP payload extracted - Length: {HttpLength}", http.Length);

        // -------- HTTP --------
        // Find header/body split: \r\n\r\n
        int headerEnd = IndexOf(http, "\r\n\r\n"u8);
        if (headerEnd < 0) 
        {
            _logger?.LogWarning("No HTTP header/body separator found. Not a complete HTTP message.");
            return null;
        }
        var headerBytes = http.Slice(0, headerEnd);
        var bodyBytes = http.Slice(headerEnd + 4);
        _logger?.LogDebug("HTTP headers found - Header length: {HeaderLength}, Body length: {BodyLength}", headerBytes.Length, bodyBytes.Length);

        // Parse headers into dictionary
        var headers = ParseHttpHeaders(headerBytes);
        bool isChunked = headers.TryGetValue("transfer-encoding", out var te) && te.Contains("chunked", StringComparison.OrdinalIgnoreCase);
        int contentLength = headers.TryGetValue("content-length", out var cl) && int.TryParse(cl, out var len) ? len : -1;
        _logger?.LogDebug("HTTP headers parsed - Chunked: {IsChunked}, Content-Length: {ContentLength}", isChunked, contentLength);

        byte[] bodyBuf;
        if (isChunked)
        {
            _logger?.LogDebug("Processing chunked HTTP body");
            if (!TryDechunk(bodyBytes, out bodyBuf)) 
            {
                _logger?.LogError("Failed to dechunk HTTP body");
                return null;
            }
            _logger?.LogDebug("Successfully dechunked HTTP body - Length: {BodyLength}", bodyBuf.Length);
        }
        else
        {
            if (contentLength >= 0)
            {
                if (bodyBytes.Length < contentLength) 
                {
                    _logger?.LogWarning("HTTP body too short. Expected: {Expected}, Available: {Available}", contentLength, bodyBytes.Length);
                    return null;
                }
                bodyBuf = bodyBytes[..contentLength].ToArray();
                _logger?.LogDebug("HTTP body extracted with Content-Length - Length: {BodyLength}", bodyBuf.Length);
            }
            else
            {
                // No CL, assume rest of segment is body
                bodyBuf = bodyBytes.ToArray();
                _logger?.LogDebug("HTTP body extracted without Content-Length - Length: {BodyLength}", bodyBuf.Length);
            }
        }

        // If body is binary (no XML), support 8-byte fallback: [float zoom][float measurement]
        if (bodyBuf.Length >= 8 && Array.IndexOf(bodyBuf, (byte)'<') < 0)
        {
            _logger?.LogDebug("Binary HTTP body detected (no XML), extracting zoom/measurement from first 8 bytes");
            var zoomF = BitConverter.ToSingle(bodyBuf.AsSpan(0, 4));
            var measurementF = BitConverter.ToSingle(bodyBuf.AsSpan(4, 4));
            _logger?.LogDebug("Binary body parsing successful - zoom: {Zoom}, measurement: {Measurement}", zoomF, measurementF);
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
        if (xmlStart < 0) 
        {
            _logger?.LogWarning("No XML content found in HTTP body. Body length: {BodyLength}", body.Length);
            return null;
        }
        string xml = body[xmlStart..].Trim();
        _logger?.LogDebug("XML content found - Start position: {XmlStart}, XML length: {XmlLength}", xmlStart, xml.Length);

        // Quick completeness check for SOAP Envelope markers (not foolproof)
        if (!LooksLikeCompleteSoap(xml)) 
        {
            _logger?.LogWarning("XML does not appear to be a complete SOAP envelope");
            return null;
        }

            // -------- SOAP/XML --------
            _logger?.LogDebug("Parsing SOAP/XML content. XML length: {Length} characters", xml.Length);
            
            XDocument doc;
            try { doc = XDocument.Parse(xml, LoadOptions.None); }
            catch (Exception ex) 
            { 
                _logger?.LogWarning("Failed to parse XML content: {Error}", ex.Message);
                return null; 
            }

        var ns = new XmlNs(doc);

        // Header/Body nodes
        var env = doc.Root;
        if (env is null) 
        {
            _logger?.LogError("SOAP document has no root element");
            return null;
        }
        var header = env.Element(ns.s + "Header") ?? env.Element(ns.sa + "Header") ?? env.Element(ns.soap + "Header");
        var bodyEl = env.Element(ns.s + "Body") ?? env.Element(ns.sa + "Body") ?? env.Element(ns.soap + "Body");
        if (header is null || bodyEl is null) 
        {
            _logger?.LogError("SOAP envelope missing Header or Body element");
            return null;
        }
        _logger?.LogDebug("SOAP Header and Body elements found");

        // MessageID
        var msgIdVal = header.Element(ns.a + "MessageID")?.Value
                    ?? header.Element(ns.wsa5 + "MessageID")?.Value
                    ?? header.Element(ns.wsa + "MessageID")?.Value;
        if (string.IsNullOrWhiteSpace(msgIdVal)) 
        {
            _logger?.LogError("SOAP message missing MessageID in header");
            return null;
        }
        string cleanMsgId = ExtractUuid(msgIdVal); // urn:uuid:<uuid> -> <uuid>
        _logger?.LogDebug("MessageID extracted: {MessageId}", cleanMsgId);

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
            var entity = new OnVIFPacketEntity
            {
                Id = Guid.NewGuid(),
                Timestamp = DateTime.UtcNow,          // if your entity uses ulong identity timestamp, remove this
                Type = type == "RPT",                 // you can reinterpret: true=RPT (device report), false=CMD
                Description = description,
                Zoom = zoom,
                Measurement = measurement ?? 0f       // or null if your model allows
            };

            _logger?.LogInformation("Successfully parsed OnVIF packet - Type: {Type}, Description: {Description}, Profile: {Profile}, Zoom: {Zoom}, Measurement: {Measurement}", 
                type, description, profile, zoom, measurement);
            
            return entity;
        }
        catch (Exception ex)
        {
            _logger?.LogError(ex, "Error parsing OnVIF packet. Packet length: {Length} bytes, Raw data: {Data}", 
                rawPacket.Length, BitConverter.ToString(rawPacket.ToArray()).Replace("-", ""));
            return null;
        }
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
        int chunkCount = 0;
        
        _logger?.LogDebug("Starting chunked encoding dechunking. Input length: {Length}", chunked.Length);
        
        while (true)
        {
            int lineEnd = IndexOf(chunked[idx..], "\r\n"u8);
            if (lineEnd < 0) 
            { 
                _logger?.LogError("Chunked encoding error: No line end found at position {Position}", idx);
                body = Array.Empty<byte>(); 
                return false; 
            }
            int hexLenStart = idx;
            int hexLenEnd = idx + lineEnd;
            string hexStr = Encoding.ASCII.GetString(chunked.Slice(hexLenStart, lineEnd));
            if (!int.TryParse(hexStr.Split(';')[0], System.Globalization.NumberStyles.HexNumber, null, out int size))
            {
                _logger?.LogError("Chunked encoding error: Invalid chunk size '{HexStr}' at position {Position}", hexStr, idx);
                body = Array.Empty<byte>(); 
                return false;
            }
            idx = hexLenEnd + 2; // skip \r\n
            if (size == 0) 
            {
                _logger?.LogDebug("Chunked encoding completed. Processed {ChunkCount} chunks, total size: {TotalSize}", chunkCount, ms.Length);
                break;
            }
            if (chunked.Length < idx + size + 2) 
            { 
                _logger?.LogError("Chunked encoding error: Chunk {ChunkCount} size {Size} exceeds available data at position {Position}", chunkCount, size, idx);
                body = Array.Empty<byte>(); 
                return false; 
            }
            ms.Write(chunked.Slice(idx, size));
            idx += size;
            chunkCount++;
            
            // trailing \r\n
            if (chunked.Length < idx + 2 || chunked[idx] != (byte)'\r' || chunked[idx + 1] != (byte)'\n')
            {
                _logger?.LogError("Chunked encoding error: Missing trailing CRLF after chunk {ChunkCount} at position {Position}", chunkCount, idx);
                body = Array.Empty<byte>(); 
                return false;
            }
            idx += 2;
        }
        // final CRLF after 0-size chunk (optional headers ignored)
        // try to consume optional "\r\n"
        body = ms.ToArray();
        _logger?.LogDebug("Chunked encoding dechunking successful. Final body size: {BodySize}", body.Length);
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
