using System.Globalization;
using System.Xml.Linq;
using Microsoft.Extensions.Logging;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Utils.Exceptions;
using PacketDotNet;
using PacketProcessing.Utils.Parsers.OnVifUtilities;

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

        private static readonly StreamReassembler _streamReassembler = new();

        private static readonly HashSet<string> DayIRTokens = new(StringComparer.OrdinalIgnoreCase) { Constants.Constants.ONVIF_XML_DAY, Constants.Constants.ONVIF_XML_NIGHT};

        /// <summary>
        /// Parses a single ONVIF HTTP SOAP message from a raw packet (Ethernet frame).
        /// Handles TCP stream reassembly for fragmented HTTP messages.
        /// Returns null if the buffer doesn't look like an ONVIF SOAP request/response.
        /// </summary>
        public static OnVIFPacketEntity? Parse(ReadOnlySpan<byte> rawPacket)
        {
            try{

                var packet = Packet.ParsePacket(LinkLayers.Ethernet, rawPacket.ToArray());
                var ipSection = packet.Extract<IPv4Packet>();
                var ipSrc = ipSection.SourceAddress.ToString();
                var ipDst = ipSection.DestinationAddress.ToString();
                var tcpSection = ipSection.Extract<TcpPacket>();
                var tcpSrc = tcpSection.SourcePort;
                var tcpDst = tcpSection.DestinationPort;
                var tcpSeq = (int)tcpSection.SequenceNumber;
                var data = tcpSection.PayloadData;

                if (data.Length==0){
                    _logger?.LogDebug("OnVIF packet is too short to contain any data");
                    return null;
                }

                _streamReassembler.AddSegment(ipSrc, tcpSrc, ipDst, tcpDst, tcpSeq, data);

                string? body = _streamReassembler.TryReassembleXml(ipSrc, tcpSrc, ipDst, tcpDst);

                if (body==null){
                    _logger?.LogDebug("OnVIF packet is not completed yet, waiting for more packets");
                    throw new ParserStreamNotCompletedException("OnVIF packet is not completed yet");
                }
                // On this point onwards is guaranteed that the string is structured as an XML document
                XDocument xmlBody = XDocument.Parse(body);

                var isCmd = ipSrc != Constants.Constants.ONVIF_REPORT_IP;

                // If the profile token is present, then it's a FOV_REQ 
                if (TryExtractProfileToken(xmlBody, out string token))
                {
                    // If token exist in set, then it must be "day" or "night_combined"
                    if (DayIRTokens.Contains(token))
                    {
                        return new OnVIFPacketEntity {
                            Id = Guid.NewGuid(),
                            Timestamp = DateTime.UtcNow,
                            IsCmd = isCmd,
                            Description = Constants.Constants.ONVIF_FOV_REQ,
                            Zoom = null,
                            Measurement = null,
                        };
                    }
                }

                // If the zoom is present, then it's a FOV_STS
                else if (TryExtractZoomX(xmlBody, out double zoom)) {
                    return new OnVIFPacketEntity {
                        Id = Guid.NewGuid(),
                        Timestamp = DateTime.UtcNow,
                        IsCmd = isCmd,
                        Description = Constants.Constants.ONVIF_FOV_STS,
                        Zoom = zoom,
                        Measurement = null,
                    };
                }

                // Token not in map, check if LRF
                else if (TryExtractGetPower(xmlBody, out string power)) 
                {
                    // If power is laster_range_finder, then it's a LRF_REQ
                    if (power == Constants.Constants.ONVIF_XML_LRF)
                    {
                        return new OnVIFPacketEntity {
                            Id = Guid.NewGuid(),
                            Timestamp = DateTime.UtcNow,
                            IsCmd = isCmd,
                            Description = Constants.Constants.ONVIF_LRF_REQ,
                            Zoom = null,
                            Measurement = null,
                        };
                    }
                }

                // If power is not laster_range_finder, then it's a LRF_STS
                else if (TryExtractMeasurement(xmlBody, out double measurement))
                {
                    return new OnVIFPacketEntity {
                        Id = Guid.NewGuid(),
                        Timestamp = DateTime.UtcNow,
                        IsCmd = isCmd,
                        Description = Constants.Constants.ONVIF_LRF_STS,
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
        private static bool TryExtractZoomX(XDocument xmlBody, out double value)
        {
            value = default;
            var zoom = xmlBody.Descendants().FirstOrDefault(e => e.Name.LocalName == "Zoom");
            if (zoom == null) return false;
            var xAttr = zoom.Attribute("x")?.Value;
            if (string.IsNullOrEmpty(xAttr)) return false;
            return double.TryParse(xAttr, NumberStyles.Float, CultureInfo.InvariantCulture, out value);
        }

        // Try to extract <Measurement ...> value (float) if present.
        private static bool TryExtractMeasurement(XDocument xmlBody, out double value)
        {
            value = default;
            var measurement = xmlBody.Descendants().FirstOrDefault(e => e.Name.LocalName == "Measurement");
            if (measurement == null) return false;
            var measText = measurement.Value;
            
            // Handle error sentinel [Error: 1001] → -1000
            if (measText.Contains("Error", StringComparison.OrdinalIgnoreCase))
            {
                value = -1000.0d;
                return true;
            }
            
            return double.TryParse(measText, NumberStyles.Float, CultureInfo.InvariantCulture, out value);
        }

        // Try to extract <tt:Power ...> value (string) if present.
        private static bool TryExtractGetPower(XDocument xmlBody, out string value)
        {
            value = string.Empty;
            var power = xmlBody.Descendants().FirstOrDefault(e => e.Name.LocalName == "Power");
            if (power == null) return false;
            value = power.Attribute("name")?.Value ?? string.Empty;
            return true;
        }
    }
}
