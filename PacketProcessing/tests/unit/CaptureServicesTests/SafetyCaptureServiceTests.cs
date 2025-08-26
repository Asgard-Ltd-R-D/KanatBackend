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
/// Tests for SafetyCaptureService to verify packet capture, parsing, and channel writing
/// </summary>
public class SafetyCaptureServiceTests : BaseCaptureServiceTests<SafetyPacketEntity>
{
    private readonly SafetyCaptureService _safetyCaptureService;
    private readonly Mock<IConfigurationSection> _dataPipeSectionMock;

    public SafetyCaptureServiceTests()
    {
        // Setup configuration for safety data pipe
        _dataPipeSectionMock = CreateMockConfigurationSection("SafetyDataPipe", "TCP", new[] { "192.168.1.200", "192.168.1.201" }, 500);
        _configurationMock.Setup(x => x.GetSection("DataPipes:SafetyDataPipe")).Returns(_dataPipeSectionMock);

        // Create the safety capture service
        _safetyCaptureService = CreateCaptureService("SafetyDataPipe");
    }

    protected override SafetyCaptureService CreateCaptureService(string dataPipeName)
    {
        return new SafetyCaptureService(_loggerMock.Object, _configurationMock.Object, _activeDevices, _testChannel);
    }

    protected override string GetExpectedFilter(string protocol, string[] ips)
    {
        var ipFilters = string.Join(" or ", ips.Select(ip => $"host {ip}"));
        return $"{protocol.ToLower()} and ({ipFilters})";
    }

    protected override string CreateValidTestPayload()
    {
        return """{"type": true, "opcode": "SAFETY_ALERT", "opcodedescription": "Safety system alert", "axis": 2, "floatvalue": 0.95}""";
    }

    protected override string CreateInvalidTestPayload()
    {
        return """{"invalid": "payload", "missing": "required_fields"}""";
    }

    [Fact]
    public void Constructor_ShouldInitializeWithCorrectConfiguration()
    {
        // Act & Assert
        _safetyCaptureService.Should().NotBeNull();
        _safetyCaptureService.IsCapturing.Should().BeFalse();
    }

    [Fact]
    public void ParseSafetyPacket_WithValidJsonPayload_ShouldParseCorrectly()
    {
        // Arrange
        var validPayload = CreateValidTestPayload();
        var payloadBytes = CreateTestPacketPayload(validPayload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("SAFETY_ALERT");
        result.OpCodeDescription.Should().Be("Safety system alert");
        result.Axis.Should().Be(2);
        result.FloatValue.Should().Be(0.95f);
    }

    [Fact]
    public void ParseSafetyPacket_WithInvalidJsonPayload_ShouldReturnNull()
    {
        // Arrange
        var invalidPayload = CreateInvalidTestPayload();
        var payloadBytes = CreateTestPacketPayload(invalidPayload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().BeNull();
    }

    [Fact]
    public void ParseSafetyPacket_WithEmptyPayload_ShouldReturnNull()
    {
        // Arrange
        var emptyPayload = new byte[0];

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(emptyPayload);

        // Assert
        result.Should().BeNull();
    }

    [Fact]
    public void ParseSafetyPacket_WithNullPayload_ShouldReturnNull()
    {
        // Arrange
        byte[]? nullPayload = null;

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(nullPayload);

        // Assert
        result.Should().BeNull();
    }

    [Fact]
    public void ParseSafetyPacket_WithPartialJsonPayload_ShouldParseAvailableFields()
    {
        // Arrange
        var partialPayload = """{"type": false, "opcode": "PARTIAL_SAFETY_DATA"}""";
        var payloadBytes = CreateTestPacketPayload(partialPayload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeFalse();
        result.OpCode.Should().Be("PARTIAL_SAFETY_DATA");
        result.OpCodeDescription.Should().BeEmpty(); // Default value
        result.Axis.Should().Be(0); // Default value
        result.FloatValue.Should().Be(0.0f); // Default value
    }

    [Fact]
    public void ParseSafetyPacket_WithDifferentDataTypes_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "SAFETY_TEST", "opcodedescription": "Safety Test Description", "axis": 42, "floatvalue": -123.456}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("SAFETY_TEST");
        result.OpCodeDescription.Should().Be("Safety Test Description");
        result.Axis.Should().Be(42);
        result.FloatValue.Should().Be(-123.456f);
    }

    [Fact]
    public void ParseSafetyPacket_WithCaseInsensitiveFieldNames_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"TYPE": true, "OPCODE": "SAFETY_CASE_TEST", "OPCODEDESCRIPTION": "Safety Case Test", "AXIS": 5, "FLOATVALUE": 99.9}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("SAFETY_CASE_TEST");
        result.OpCodeDescription.Should().Be("Safety Case Test");
        result.Axis.Should().Be(5);
        result.FloatValue.Should().Be(99.9f);
    }

    [Fact]
    public void ParseSafetyPacket_WithMalformedJson_ShouldReturnNull()
    {
        // Arrange
        var malformedJson = """{"type": true, "opcode": "SAFETY_TEST", "missing": "closing brace" """;
        var payloadBytes = CreateTestPacketPayload(malformedJson);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().BeNull();
    }

    [Fact]
    public void ParseSafetyPacket_WithNonJsonPayload_ShouldReturnNull()
    {
        // Arrange
        var nonJsonPayload = "This is not JSON at all";
        var payloadBytes = CreateTestPacketPayload(nonJsonPayload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().BeNull();
    }

    [Fact]
    public void ParseSafetyPacket_WithSpecialCharactersInStrings_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "SAFETY_SPECIAL_CHARS", "opcodedescription": "Safety test with \"quotes\" and \n newlines", "axis": 0, "floatvalue": 0.0}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.OpCode.Should().Be("SAFETY_SPECIAL_CHARS");
        result.OpCodeDescription.Should().Be("Safety test with \"quotes\" and \n newlines");
    }

    [Fact]
    public void ParseSafetyPacket_WithNumericStringValues_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": "true", "opcode": "123", "opcodedescription": "456", "axis": "7", "floatvalue": "8.9"}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue(); // String "true" should be parsed as boolean true
        result.OpCode.Should().Be("123");
        result.OpCodeDescription.Should().Be("456");
        result.Axis.Should().Be(7);
        result.FloatValue.Should().Be(8.9f);
    }

    [Fact]
    public void ParseSafetyPacket_WithVeryLargeValues_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "SAFETY_LARGE_VALUES", "opcodedescription": "Safety test with large values", "axis": 2147483647, "floatvalue": 3.402823E+38}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Axis.Should().Be(int.MaxValue);
        result.FloatValue.Should().Be(float.MaxValue);
    }

    [Fact]
    public void ParseSafetyPacket_WithNegativeValues_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": false, "opcode": "SAFETY_NEGATIVE", "opcodedescription": "Safety negative values test", "axis": -42, "floatvalue": -123.456}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeFalse();
        result.Axis.Should().Be(-42);
        result.FloatValue.Should().Be(-123.456f);
    }

    [Fact]
    public void ParseSafetyPacket_WithZeroValues_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": false, "opcode": "SAFETY_ZERO", "opcodedescription": "Safety zero values test", "axis": 0, "floatvalue": 0.0}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeFalse();
        result.Axis.Should().Be(0);
        result.FloatValue.Should().Be(0.0f);
    }

    [Fact]
    public void ParseSafetyPacket_WithUnicodeCharacters_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "SAFETY_UNICODE", "opcodedescription": "Safety test with unicode: 🚨⚠️🛡️", "axis": 1, "floatvalue": 1.0}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.OpCode.Should().Be("SAFETY_UNICODE");
        result.OpCodeDescription.Should().Be("Safety test with unicode: 🚨⚠️🛡️");
    }

    [Fact]
    public void ParseSafetyPacket_WithVeryLongStrings_ShouldParseCorrectly()
    {
        // Arrange
        var longString = new string('S', 1000);
        var payload = $"""{{"type": true, "opcode": "{longString}", "opcodedescription": "{longString}", "axis": 1, "floatvalue": 1.0}}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.OpCode.Should().Be(longString);
        result.OpCodeDescription.Should().Be(longString);
    }

    [Fact]
    public void ParseSafetyPacket_WithScientificNotation_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "SAFETY_SCIENTIFIC", "opcodedescription": "Safety scientific notation test", "axis": 1, "floatvalue": 1.23e-4}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.FloatValue.Should().Be(1.23e-4f);
    }

    [Fact]
    public void ParseSafetyPacket_WithExtraFields_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "SAFETY_EXTRA_FIELDS", "opcodedescription": "Safety extra fields test", "axis": 1, "floatvalue": 1.0, "extraField1": "value1", "extraField2": 42}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("SAFETY_EXTRA_FIELDS");
        result.OpCodeDescription.Should().Be("Safety extra fields test");
        result.Axis.Should().Be(1);
        result.FloatValue.Should().Be(1.0f);
    }

    [Fact]
    public void ParseSafetyPacket_WithNullValues_ShouldUseDefaults()
    {
        // Arrange
        var payload = """{"type": null, "opcode": null, "opcodedescription": null, "axis": null, "floatvalue": null}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeFalse(); // Default value
        result.OpCode.Should().BeEmpty(); // Default value
        result.OpCodeDescription.Should().BeEmpty(); // Default value
        result.Axis.Should().Be(0); // Default value
        result.FloatValue.Should().Be(0.0f); // Default value
    }

    [Fact]
    public void ParseSafetyPacket_WithMixedDataTypes_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": "true", "opcode": 123, "opcodedescription": true, "axis": "42", "floatvalue": "3.14"}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue(); // String "true" parsed as boolean
        result.OpCode.Should().Be("123"); // Number converted to string
        result.OpCodeDescription.Should().Be("True"); // Boolean converted to string
        result.Axis.Should().Be(42); // String "42" parsed as int
        result.FloatValue.Should().Be(3.14f); // String "3.14" parsed as float
    }

    [Fact]
    public void ParseSafetyPacket_WithSafetySpecificValues_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "EMERGENCY_STOP", "opcodedescription": "Emergency stop activated", "axis": 3, "floatvalue": 1.0}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("EMERGENCY_STOP");
        result.OpCodeDescription.Should().Be("Emergency stop activated");
        result.Axis.Should().Be(3);
        result.FloatValue.Should().Be(1.0f);
    }

    [Fact]
    public void ParseSafetyPacket_WithSafetyThresholdValues_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": false, "opcode": "THRESHOLD_WARNING", "opcodedescription": "Safety threshold warning", "axis": 1, "floatvalue": 0.85}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _safetyCaptureService.ParseSafetyPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeFalse();
        result.OpCode.Should().Be("THRESHOLD_WARNING");
        result.OpCodeDescription.Should().Be("Safety threshold warning");
        result.Axis.Should().Be(1);
        result.FloatValue.Should().Be(0.85f);
    }
}
