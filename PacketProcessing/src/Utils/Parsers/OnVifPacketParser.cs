using System.Buffers.Binary;
using System.Globalization;
using System.Net;
using System.Text;
using System.Xml.Linq;
using Microsoft.Extensions.Logging;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Utils.Exceptions;
using static PacketProcessing.Utils.Parsers.HttpXmlReassembler;

namespace PacketProcessing.Utils.Parsers
{
    /// <summary>
    /// ONVIF/HTTP(S)/SOAP parser.
    /// Extracts: IsCmd, Description (CMD/RPT verb), Zoom (0.xxx for DAY/IR), Measurement (LRF or -1000 on error).
    /// Works directly on a captured TCP payload that includes HTTP headers + SOAP body.
    /// </summary>
    public static class OnVifPacketParser
    {
        private static ILogger? _logger;
        public static void SetLogger(ILogger logger)
        {
            _logger = logger;
        }

        private const string REPORT_IP = "132.8.7.1";

        private static readonly HashSet<string> ProfileTokens = new(StringComparer.OrdinalIgnoreCase) { "day", "night_combined" };

        /// <summary>
        /// Parses a single ONVIF HTTP SOAP message from a raw packet (Ethernet frame).
        /// Handles TCP stream reassembly for fragmented HTTP messages.
        /// Returns null if the buffer doesn't look like an ONVIF SOAP request/response.
        /// </summary>
        public static OnVIFPacketEntity? Parse(ReadOnlySpan<byte> rawPacket)
        {
            try 
            {
                // Assemble the complete HTTP body
                // Throws ParserStreamNotCompletedException if the stream is not complete
                // Returns the complete HTTP body as ReadOnlyMemory<byte>
                XDocument soapBody = AssembleXmlOrThrow(rawPacket);

                // --- Check if the packet is long enough to contain an Ethernet + IP + TCP/CapTrack Data Payload ---
                if (rawPacket.Length < 54)
                {
                    _logger?.LogWarning("Packet too short to contain an Ethernet + IP + TCP/CapTrack Data Payload. Raw Packet Length: {RawPacketLength}", rawPacket.Length);
                    return null;
                }

                // --- Get the source IP address, if it's the report IP, then it's a command, otherwise it's a report ---
                var isCmd = false;
                if (TryGetSrcIp(rawPacket, out string src))
                {
                    isCmd = src != REPORT_IP;
                }

                // If the profile token is present, then it's a FOV_REQ 
                if (TryExtractProfileToken(soapBody, out string token))
                {
                    // If token exist in set, then it must be "day" or "night_combined"
                    if (ProfileTokens.Contains(token))
                    {
                        return new OnVIFPacketEntity {
                            Id = Guid.NewGuid(),
                            Timestamp = DateTime.UtcNow,
                            IsCmd = isCmd,
                            Description = "FOV_REQ",
                            Zoom = null,
                            Measurement = 1,
                        };
                    }
                }

                // If the zoom is present, then it's a FOV_STS
                else if (TryExtractZoomX(soapBody, out float zoom)) {
                    return new OnVIFPacketEntity {
                        Id = Guid.NewGuid(),
                        Timestamp = DateTime.UtcNow,
                        IsCmd = isCmd,
                        Description = "FOV_STS",
                        Zoom = zoom,
                        Measurement = null,
                    };
                }

                // Token not in map, check if LRF
                else if (TryExtractGetPower(soapBody, out string power)) 
                {
                    // If power is laster_range_finder, then it's a LRF_REQ
                    if (power == "laster_range_finder")
                    {
                        return new OnVIFPacketEntity {
                            Id = Guid.NewGuid(),
                            Timestamp = DateTime.UtcNow,
                            IsCmd = isCmd,
                            Description = "LRF_REQ",
                            Zoom = null,
                            Measurement = null,
                        };
                    }
                }

                // If power is not laster_range_finder, then it's a LRF_STS
                else if (TryExtractMeasurement(soapBody, out float measurement))
                {
                    return new OnVIFPacketEntity {
                        Id = Guid.NewGuid(),
                        Timestamp = DateTime.UtcNow,
                        IsCmd = isCmd,
                        Description = "LRF_STS",
                        Zoom = null,
                        Measurement = measurement,
                    };
                }

                // If no token or power found, return null
                return null;

            }
            catch (ParserStreamNotCompletedException ex)
            {
                throw new ParserStreamNotCompletedException(ex.Message);
            }
            catch (Exception ex)
            {
                if (_logger?.IsEnabled(LogLevel.Debug) ?? false)
                    _logger.LogDebug(ex, "Error parsing motion packet. Length: {Length} bytes", rawPacket.Length);
                return null;
            }
        }

        // Try to extract the source IP address from the frame.
        private static bool TryGetSrcIp(ReadOnlySpan<byte> frame, out string src)
        {
            src = string.Empty;
            if (frame.Length < 14) return false;

            ushort etherType = (ushort)((frame[12] << 8) | frame[13]);
            int ipOffset = 14;

            // VLAN tagged?
            if (etherType == 0x8100)
            {
                if (frame.Length < 18) return false;
                etherType = (ushort)((frame[16] << 8) | frame[17]);
                ipOffset = 18;
            }

            // Must be IPv4
            if (etherType != 0x0800 || frame.Length < ipOffset + 20)
                return false;

            var ip = frame[ipOffset..];
            int ihl = (ip[0] & 0x0F) * 4;
            if (ihl < 20 || frame.Length < ipOffset + ihl)
                return false;

            var srcBytes = ip.Slice(12, 4).ToArray();
            src = new IPAddress(srcBytes).ToString();
            return true;
        }

        // Try to extract <ProfileToken>day</ProfileToken> value (string) if present.
        private static bool TryExtractProfileToken(XDocument soapBody, out string token)
        {
            token = string.Empty;
            var profileToken = soapBody.Descendants().FirstOrDefault(e => e.Name.LocalName == "ProfileToken");
            if (profileToken == null) return false;
            token = profileToken.Value;
            return true;
        }

        // Try to extract <tt:Zoom x="0.123" ...> value (float) if present.
        private static bool TryExtractZoomX(XDocument soapBody, out float value)
        {
            value = default;
            var zoom = soapBody.Descendants().FirstOrDefault(e => e.Name.LocalName == "Zoom");
            if (zoom == null) return false;
            var xAttr = zoom.Attribute("x")?.Value;
            if (string.IsNullOrEmpty(xAttr)) return false;
            return float.TryParse(xAttr, NumberStyles.Float, CultureInfo.InvariantCulture, out value);
        }

        // Try to extract <Measurement ...> value (float) if present.
        private static bool TryExtractMeasurement(XDocument soapBody, out float value)
        {
            value = default;
            var measurement = soapBody.Descendants().FirstOrDefault(e => e.Name.LocalName == "Measurement");
            if (measurement == null) return false;
            var measText = measurement.Value;
            
            // Handle error sentinel [Error: 1001] → -1000
            if (measText.IndexOf("Error", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                value = -1000f;
                return true;
            }
            
            return float.TryParse(measText, NumberStyles.Float, CultureInfo.InvariantCulture, out value);
        }

        // Try to extract <tt:Power ...> value (string) if present.
        private static bool TryExtractGetPower(XDocument soapBody, out string value)
        {
            value = string.Empty;
            var power = soapBody.Descendants().FirstOrDefault(e => e.Name.LocalName == "Power");
            if (power == null) return false;
            value = power.Attribute("name")?.Value ?? string.Empty;
            return true;
        }
    }
}
