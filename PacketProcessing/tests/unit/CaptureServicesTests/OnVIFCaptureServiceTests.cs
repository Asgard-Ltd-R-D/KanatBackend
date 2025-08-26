using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Collections.Concurrent;
using System.Threading.Channels;
using PacketProcessing.Entities;
using PacketProcessing.Entities.Packet;
using PacketProcessing.Services.Networking;
using Moq;
using FluentAssertions;
using Xunit;
using LibPcap;

namespace PacketProcessing.Tests.CaptureServicesTests;

/// <summary>
/// Tests for OnVIFCaptureService to verify packet capture, parsing, and channel writing
/// </summary>
public class OnVIFCaptureServiceTests : BaseCaptureServiceTests<OnVIFPacketEntity>
{
    private readonly OnVIFCaptureService _onvifCaptureService;
    private readonly Mock<IConfigurationSection> _dataPipeSectionMock;

    public OnVIFCaptureServiceTests()
    {
        // Setup configuration for OnVIF data pipe
        _dataPipeSectionMock = CreateMockConfigurationSection("OnVIFDataPipe", "HTTP", new[] { "192.168.1.150", "192.168.1.151" }, 750);
        _configurationMock.Setup(x => x.GetSection("DataPipes:OnVIFDataPipe")).Returns(_dataPipeSectionMock);

        // Create the OnVIF capture service
        _onvifCaptureService = CreateCaptureService("OnVIFDataPipe");
    }

    protected override OnVIFCaptureService CreateCaptureService(string dataPipeName)
    {
        return new OnVIFCaptureService(_loggerMock.Object, _configurationMock.Object, _activeDevices, _testChannel);
    }

    protected override string GetExpectedFilter(string protocol, string[] ips)
    {
        var ipFilters = string.Join(" or ", ips.Select(ip => $"host {ip}"));
        return $"{protocol.ToLower()} and ({ipFilters})";
    }

    protected override string CreateValidTestPayload()
    {
        return """{"type": true, "opcode": "ONVIF_EVENT", "opcodedescription": "OnVIF camera event", "axis": 3, "floatvalue": 0.88}""";
    }

    protected override string CreateInvalidTestPayload()
    {
        return """{"invalid": "payload", "missing": "required_fields"}""";
    }

    [Fact]
    public void Constructor_ShouldInitializeWithCorrectConfiguration()
    {
        // Act & Assert
        _onvifCaptureService.Should().NotBeNull();
        _onvifCaptureService.IsCapturing.Should().BeFalse();
    }

    [Fact]
    public void ParseOnVIFPacket_WithValidJsonPayload_ShouldParseCorrectly()
    {
        // Arrange
        var validPayload = CreateValidTestPayload();
        var payloadBytes = CreateTestPacketPayload(validPayload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("ONVIF_EVENT");
        result.OpCodeDescription.Should().Be("OnVIF camera event");
        result.Axis.Should().Be(3);
        result.FloatValue.Should().Be(0.88f);
    }

    [Fact]
    public void ParseOnVIFPacket_WithInvalidJsonPayload_ShouldReturnNull()
    {
        // Arrange
        var invalidPayload = CreateInvalidTestPayload();
        var payloadBytes = CreateTestPacketPayload(invalidPayload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().BeNull();
    }

    [Fact]
    public void ParseOnVIFPacket_WithEmptyPayload_ShouldReturnNull()
    {
        // Arrange
        var emptyPayload = new byte[0];

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(emptyPayload);

        // Assert
        result.Should().BeNull();
    }

    [Fact]
    public void ParseOnVIFPacket_WithNullPayload_ShouldReturnNull()
    {
        // Arrange
        byte[]? nullPayload = null;

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(nullPayload);

        // Assert
        result.Should().BeNull();
    }

    [Fact]
    public void ParseOnVIFPacket_WithPartialJsonPayload_ShouldParseAvailableFields()
    {
        // Arrange
        var partialPayload = """{"type": false, "opcode": "PARTIAL_ONVIF_DATA"}""";
        var payloadBytes = CreateTestPacketPayload(partialPayload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeFalse();
        result.OpCode.Should().Be("PARTIAL_ONVIF_DATA");
        result.OpCodeDescription.Should().BeEmpty(); // Default value
        result.Axis.Should().Be(0); // Default value
        result.FloatValue.Should().Be(0.0f); // Default value
    }

    [Fact]
    public void ParseOnVIFPacket_WithDifferentDataTypes_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "ONVIF_TEST", "opcodedescription": "OnVIF Test Description", "axis": 42, "floatvalue": -123.456}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("ONVIF_TEST");
        result.OpCodeDescription.Should().Be("OnVIF Test Description");
        result.Axis.Should().Be(42);
        result.FloatValue.Should().Be(-123.456f);
    }

    [Fact]
    public void ParseOnVIFPacket_WithCaseInsensitiveFieldNames_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"TYPE": true, "OPCODE": "ONVIF_CASE_TEST", "OPCODEDESCRIPTION": "OnVIF Case Test", "AXIS": 5, "FLOATVALUE": 99.9}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("ONVIF_CASE_TEST");
        result.OpCodeDescription.Should().Be("OnVIF Case Test");
        result.Axis.Should().Be(5);
        result.FloatValue.Should().Be(99.9f);
    }

    [Fact]
    public void ParseOnVIFPacket_WithMalformedJson_ShouldReturnNull()
    {
        // Arrange
        var malformedJson = """{"type": true, "opcode": "ONVIF_TEST", "missing": "closing brace" """;
        var payloadBytes = CreateTestPacketPayload(malformedJson);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().BeNull();
    }

    [Fact]
    public void ParseOnVIFPacket_WithNonJsonPayload_ShouldReturnNull()
    {
        // Arrange
        var nonJsonPayload = "This is not JSON at all";
        var payloadBytes = CreateTestPacketPayload(nonJsonPayload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().BeNull();
    }

    [Fact]
    public void ParseOnVIFPacket_WithSpecialCharactersInStrings_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "ONVIF_SPECIAL_CHARS", "opcodedescription": "OnVIF test with \"quotes\" and \n newlines", "axis": 0, "floatvalue": 0.0}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.OpCode.Should().Be("ONVIF_SPECIAL_CHARS");
        result.OpCodeDescription.Should().Be("OnVIF test with \"quotes\" and \n newlines");
    }

    [Fact]
    public void ParseOnVIFPacket_WithNumericStringValues_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": "true", "opcode": "123", "opcodedescription": "456", "axis": "7", "floatvalue": "8.9"}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue(); // String "true" should be parsed as boolean true
        result.OpCode.Should().Be("123");
        result.OpCodeDescription.Should().Be("456");
        result.Axis.Should().Be(7);
        result.FloatValue.Should().Be(8.9f);
    }

    [Fact]
    public void ParseOnVIFPacket_WithVeryLargeValues_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "ONVIF_LARGE_VALUES", "opcodedescription": "OnVIF test with large values", "axis": 2147483647, "floatvalue": 3.402823E+38}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Axis.Should().Be(int.MaxValue);
        result.FloatValue.Should().Be(float.MaxValue);
    }

    [Fact]
    public void ParseOnVIFPacket_WithNegativeValues_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": false, "opcode": "ONVIF_NEGATIVE", "opcodedescription": "OnVIF negative values test", "axis": -42, "floatvalue": -123.456}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeFalse();
        result.Axis.Should().Be(-42);
        result.FloatValue.Should().Be(-123.456f);
    }

    [Fact]
    public void ParseOnVIFPacket_WithZeroValues_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": false, "opcode": "ONVIF_ZERO", "opcodedescription": "OnVIF zero values test", "axis": 0, "floatvalue": 0.0}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeFalse();
        result.Axis.Should().Be(0);
        result.FloatValue.Should().Be(0.0f);
    }

    [Fact]
    public void ParseOnVIFPacket_WithUnicodeCharacters_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "ONVIF_UNICODE", "opcodedescription": "OnVIF test with unicode: 📹🎥📷", "axis": 1, "floatvalue": 1.0}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.OpCode.Should().Be("ONVIF_UNICODE");
        result.OpCodeDescription.Should().Be("OnVIF test with unicode: 📹🎥📷");
    }

    [Fact]
    public void ParseOnVIFPacket_WithVeryLongStrings_ShouldParseCorrectly()
    {
        // Arrange
        var longString = new string('O', 1000);
        var payload = $"""{{"type": true, "opcode": "{longString}", "opcodedescription": "{longString}", "axis": 1, "floatvalue": 1.0}}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.OpCode.Should().Be(longString);
        result.OpCodeDescription.Should().Be(longString);
    }

    [Fact]
    public void ParseOnVIFPacket_WithScientificNotation_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "ONVIF_SCIENTIFIC", "opcodedescription": "OnVIF scientific notation test", "axis": 1, "floatvalue": 1.23e-4}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.FloatValue.Should().Be(1.23e-4f);
    }

    [Fact]
    public void ParseOnVIFPacket_WithExtraFields_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "ONVIF_EXTRA_FIELDS", "opcodedescription": "OnVIF extra fields test", "axis": 1, "floatvalue": 1.0, "extraField1": "value1", "extraField2": 42}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("ONVIF_EXTRA_FIELDS");
        result.OpCodeDescription.Should().Be("OnVIF extra fields test");
        result.Axis.Should().Be(1);
        result.FloatValue.Should().Be(1.0f);
    }

    [Fact]
    public void ParseOnVIFPacket_WithNullValues_ShouldUseDefaults()
    {
        // Arrange
        var payload = """{"type": null, "opcode": null, "opcodedescription": null, "axis": null, "floatvalue": null}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeFalse(); // Default value
        result.OpCode.Should().BeEmpty(); // Default value
        result.OpCodeDescription.Should().BeEmpty(); // Default value
        result.Axis.Should().Be(0); // Default value
        result.FloatValue.Should().Be(0.0f); // Default value
    }

    [Fact]
    public void ParseOnVIFPacket_WithMixedDataTypes_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": "true", "opcode": 123, "opcodedescription": true, "axis": "42", "floatvalue": "3.14"}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue(); // String "true" parsed as boolean
        result.OpCode.Should().Be("123"); // Number converted to string
        result.OpCodeDescription.Should().Be("True"); // Boolean converted to string
        result.Axis.Should().Be(42); // String "42" parsed as int
        result.FloatValue.Should().Be(3.14f); // String "3.14" parsed as float
    }

    [Fact]
    public void ParseOnVIFPacket_WithOnVIFSpecificValues_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "CAMERA_MOTION", "opcodedescription": "Camera detected motion", "axis": 2, "floatvalue": 0.92}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("CAMERA_MOTION");
        result.OpCodeDescription.Should().Be("Camera detected motion");
        result.Axis.Should().Be(2);
        result.FloatValue.Should().Be(0.92f);
    }

    [Fact]
    public void ParseOnVIFPacket_WithOnVIFCameraEvents_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": false, "opcode": "CAMERA_OFFLINE", "opcodedescription": "Camera went offline", "axis": 0, "floatvalue": 0.0}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeFalse();
        result.OpCode.Should().Be("CAMERA_OFFLINE");
        result.OpCodeDescription.Should().Be("Camera went offline");
        result.Axis.Should().Be(0);
        result.FloatValue.Should().Be(0.0f);
    }

    [Fact]
    public void ParseOnVIFPacket_WithOnVIFStreamingEvents_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "STREAM_STARTED", "opcodedescription": "Video stream started", "axis": 1, "floatvalue": 1.0}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("STREAM_STARTED");
        result.OpCodeDescription.Should().Be("Video stream started");
        result.Axis.Should().Be(1);
        result.FloatValue.Should().Be(1.0f);
    }

    [Fact]
    public void ParseOnVIFPacket_WithOnVIFPTZEvents_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "PTZ_MOVE", "opcodedescription": "PTZ camera movement", "axis": 3, "floatvalue": 0.75}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _onvifCaptureService.ParseOnVIFPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("PTZ_MOVE");
        result.OpCodeDescription.Should().Be("PTZ camera movement");
        result.Axis.Should().Be(3);
        result.FloatValue.Should().Be(0.75f);
    }
}
