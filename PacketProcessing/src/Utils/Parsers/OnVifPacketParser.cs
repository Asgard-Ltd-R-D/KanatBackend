using System.Collections.Concurrent;
using System.Text;
using System.Xml.Linq;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Utils.Parsers
{
    public static class OnVifPacketParser
    {
        // Minimal description map
        private static readonly IReadOnlyDictionary<string, (string CMD, string RPT)> Map =
            new Dictionary<string, (string, string)>(StringComparer.OrdinalIgnoreCase)
            {
                ["DAY"] = ("FOV_REQ", "FOV_STS"),
                ["IR"]  = ("FOV_REQ", "FOV_STS"),
                ["LRF"] = ("LRF_REQ", "LRF_STS"),
            };

        // Remember CMD MessageID → profile so RPT can map back (optional, but tiny)
        private static readonly ConcurrentDictionary<string, string> MsgProfile =
            new(StringComparer.OrdinalIgnoreCase);

        public static OnVIFPacketEntity? Parse(ReadOnlySpan<byte> raw)
        {
            Console.WriteLine($"Parsing OnVIF packet. Length: {raw.Length} bytes");
            if (raw.Length < 8) return null;

            // 1) Find HTTP header/body split anywhere (works for Ethernet/TCP frames too)
            int headerEnd = IndexOf(raw, "\r\n\r\n"u8);
            if (headerEnd < 0) return null;

            var headersBytes = raw[..headerEnd];
            var bodyBytes    = raw[(headerEnd + 4)..];

            // Parse a couple of headers we actually need
            var headers = ParseHeaders(headersBytes);
            bool isChunked = headers.TryGetValue("transfer-encoding", out var te) &&
                             te.Contains("chunked", StringComparison.OrdinalIgnoreCase);

            byte[] bodyBuf = isChunked ? (TryDechunk(bodyBytes, out var b) ? b : Array.Empty<byte>())
                                       : bodyBytes.ToArray();
            if (bodyBuf.Length == 0) return null;

            // 2) Binary body fast-path: first 8 bytes → [zoom][measurement]
            if (Array.IndexOf(bodyBuf, (byte)'<') < 0)
            {
                float? zoom = bodyBuf.Length >= 4 ? BitConverter.ToSingle(bodyBuf, 0) : null;
                float? meas = bodyBuf.Length >= 8 ? BitConverter.ToSingle(bodyBuf, 4) : null;

                return new OnVIFPacketEntity
                {
                    Id = Guid.NewGuid(),
                    Timestamp = DateTime.UtcNow,
                    IsCmd = true, // treat binary payloads as RPT by default
                    Description = "UNKNOWN",
                    Zoom = zoom,
                    Measurement = meas ?? 0f
                };
            }

            // 3) XML/SOAP path
            var xmlText = Encoding.UTF8.GetString(bodyBuf).Trim();
            int lt = xmlText.IndexOf('<');
            if (lt < 0) return null;
            var xml = xmlText[lt..];

            XDocument doc;
            try { doc = XDocument.Parse(xml, LoadOptions.None); }
            catch { return null; }

            var env = doc.Root;
            if (env is null) return null;

            // Light namespace setup
            var nsSoap = env.GetNamespaceOfPrefix("s") ?? env.GetNamespaceOfPrefix("SOAP-ENV") ?? "http://schemas.xmlsoap.org/soap/envelope/";
            var nsA    = env.GetNamespaceOfPrefix("a") ?? "http://www.w3.org/2005/08/addressing";
            var nsWsa5 = env.GetNamespaceOfPrefix("wsa5") ?? "http://www.w3.org/2005/08/addressing";
            var nsWsa  = env.GetNamespaceOfPrefix("wsa") ?? "http://schemas.xmlsoap.org/ws/2004/08/addressing";
            var nsTptz = env.GetNamespaceOfPrefix("tptz") ?? "http://www.onvif.org/ver20/ptz/wsdl";
            var nsTt   = env.GetNamespaceOfPrefix("tt") ?? "http://www.onvif.org/ver10/schema";

            var header = env.Element(nsSoap + "Header");
            var body   = env.Element(nsSoap + "Body");
            if (header is null || body is null) return null;

            // MessageID (optional linking CMD→RPT)
            var msgId = header.Element(nsA + "MessageID")?.Value
                     ?? header.Element(nsWsa5 + "MessageID")?.Value
                     ?? header.Element(nsWsa + "MessageID")?.Value;
            if (!string.IsNullOrEmpty(msgId) && msgId.LastIndexOf(':') is int i && i >= 0)
                msgId = msgId[(i + 1)..];

            // Determine CMD vs RPT (minimal heuristic)
            headers.TryGetValue("action", out var action);
            headers.TryGetValue("soapaction", out var soapAction);
            bool looksResponse = (!string.IsNullOrEmpty(action) && action.Contains("Response", StringComparison.OrdinalIgnoreCase))
                              || (!string.IsNullOrEmpty(soapAction) && soapAction.Contains("Response", StringComparison.OrdinalIgnoreCase))
                              || body.Descendants().Any(e => e.Name.LocalName.EndsWith("Response", StringComparison.OrdinalIgnoreCase));

            string type = looksResponse ? "RPT" : "CMD";
            string profile = "UNKNOWN";
            string description = "UNKNOWN";
            float? zoomVal = null;
            float? measVal = null;

            if (type == "CMD")
            {
                // PTZ GetStatus → ProfileToken
                var getStatus = body.Element(nsTptz + "GetStatus");
                var token = getStatus?.Element(nsTptz + "ProfileToken")?.Value
                         ?? getStatus?.Element("ProfileToken")?.Value;

                if (EqualsIgnoreCase(token, "day")) profile = "DAY";
                else if (EqualsIgnoreCase(token, "night_combined")) profile = "IR";
                else if (ContainsLocal(body, "GetPower")) profile = "LRF";

                description = Map.TryGetValue(profile, out var pair) ? pair.CMD : "UNKNOWN";
                if (!string.IsNullOrEmpty(msgId)) MsgProfile[msgId] = profile;
            }
            else
            {
                // RPT: map back or infer
                if (!string.IsNullOrEmpty(msgId) && MsgProfile.TryRemove(msgId, out var prof))
                    profile = prof;
                else if (ContainsLocal(body, "LRFMakeMeasurementResponse"))
                    profile = "LRF";

                description = Map.TryGetValue(profile, out var pair) ? pair.RPT : "UNKNOWN";

                // Zoom for DAY/IR
                if (profile is "DAY" or "IR")
                {
                    var resp = body.Element(nsTptz + "GetStatusResponse");
                    var ptz  = resp?.Element(nsTptz + "PTZStatus") ?? resp?.Element("PTZStatus");
                    var pos  = ptz?.Element(nsTt + "Position") ?? ptz?.Element("Position");
                    var zoom = pos?.Element(nsTt + "Zoom") ?? pos?.Element("Zoom");
                    var x = zoom?.Attribute("x")?.Value ?? zoom?.Attribute(XNamespace.None + "x")?.Value;
                    if (x != null && float.TryParse(x, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var z))
                        zoomVal = (float)Math.Round(z, 3);
                    else
                        zoomVal = -1;
                }

                // LRF measurement
                if (profile == "LRF")
                {
                    var lrf = body.Descendants().FirstOrDefault(e => e.Name.LocalName.Equals("LRFMakeMeasurementResponse", StringComparison.OrdinalIgnoreCase));
                    var m = lrf?.Element("Measurement")?.Value ?? lrf?.Element(XNamespace.None + "Measurement")?.Value;
                    if (m != null)
                        measVal = m == "[Error: 1001]" ? -1 : (float)Math.Round(float.Parse(m, System.Globalization.CultureInfo.InvariantCulture), 3);
                }
            }

            return new OnVIFPacketEntity
            {
                Id = Guid.NewGuid(),
                Timestamp = DateTime.UtcNow,
                IsCmd = type == "RPT",       // true=report, false=command
                Description = description,
                Zoom = zoomVal,
                Measurement = measVal ?? 0f
            };
        }

        // --- helpers (minimal) ---

        private static int IndexOf(ReadOnlySpan<byte> s, ReadOnlySpan<byte> needle)
        {
            for (int i = 0; i <= s.Length - needle.Length; i++)
                if (s.Slice(i, needle.Length).SequenceEqual(needle)) return i;
            return -1;
        }

        private static Dictionary<string, string> ParseHeaders(ReadOnlySpan<byte> headerBytes)
        {
            var d = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            var s = Encoding.ASCII.GetString(headerBytes);
            var lines = s.Split("\r\n", StringSplitOptions.RemoveEmptyEntries);
            for (int i = 1; i < lines.Length; i++)
            {
                int sep = lines[i].IndexOf(':');
                if (sep > 0) d[lines[i][..sep].Trim()] = lines[i][(sep + 1)..].Trim();
            }
            return d;
        }

        private static bool TryDechunk(ReadOnlySpan<byte> chunked, out byte[] body)
        {
            var ms = new MemoryStream();
            int idx = 0;
            while (true)
            {
                int le = IndexOf(chunked[idx..], "\r\n"u8);
                if (le < 0) { body = Array.Empty<byte>(); return false; }
                var hex = Encoding.ASCII.GetString(chunked.Slice(idx, le));
                if (!int.TryParse(hex.Split(';')[0], System.Globalization.NumberStyles.HexNumber, null, out int size))
                { body = Array.Empty<byte>(); return false; }
                idx += le + 2;
                if (size == 0) break;
                if (chunked.Length < idx + size + 2) { body = Array.Empty<byte>(); return false; }
                ms.Write(chunked.Slice(idx, size));
                idx += size + 2; // skip data + CRLF
            }
            body = ms.ToArray();
            return true;
        }

        private static bool ContainsLocal(XElement root, string localName) =>
            root.Descendants().Any(e => e.Name.LocalName.Equals(localName, StringComparison.OrdinalIgnoreCase));

        private static bool EqualsIgnoreCase(string? a, string? b) =>
            string.Equals(a, b, StringComparison.OrdinalIgnoreCase);
    }
}
