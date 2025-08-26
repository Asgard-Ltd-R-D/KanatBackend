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
/// Tests for MotionCaptureService to verify packet capture, parsing, and channel writing
/// </summary>
public class MotionCaptureServiceTests : BaseCaptureServiceTests<MotionPacketEntity>
{
    private readonly MotionCaptureService _motionCaptureService;
    private readonly Mock<IConfigurationSection> _dataPipeSectionMock;

    public MotionCaptureServiceTests()
    {
        // Setup configuration for motion data pipe
        _dataPipeSectionMock = CreateMockConfigurationSection("MotionDataPipe", "UDP", new[] { "192.168.1.100", "192.168.1.101" }, 1000);
        _configurationMock.Setup(x => x.GetSection("DataPipes:MotionDataPipe")).Returns(_dataPipeSectionMock);

        // Create the motion capture service
        _motionCaptureService = CreateCaptureService("MotionDataPipe");
    }

    protected override MotionCaptureService CreateCaptureService(string dataPipeName)
    {
        return new MotionCaptureService(_loggerMock.Object, _configurationMock.Object, _activeDevices, _testChannel);
    }

    protected override string GetExpectedFilter(string protocol, string[] ips)
    {
        var ipFilters = string.Join(" or ", ips.Select(ip => $"host {ip}"));
        return $"{protocol.ToLower()} and ({ipFilters})";
    }

    protected override string CreateValidTestPayload()
    {
        return """{"type": true, "opcode": "MOTION_DETECTED", "opcodedescription": "Motion sensor triggered", "axis": 1, "floatvalue": 0.75}""";
    }

    protected override string CreateInvalidTestPayload()
    {
        return """{"invalid": "payload", "missing": "required_fields"}""";
    }

    [Fact]
    public void Constructor_ShouldInitializeWithCorrectConfiguration()
    {
        // Act & Assert
        _motionCaptureService.Should().NotBeNull();
        _motionCaptureService.IsCapturing.Should().BeFalse();
    }

    [Fact]
    public void ParseMotionPacket_WithValidJsonPayload_ShouldParseCorrectly()
    {
        // Arrange
        var validPayload = CreateValidTestPayload();
        var payloadBytes = CreateTestPacketPayload(validPayload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("MOTION_DETECTED");
        result.OpCodeDescription.Should().Be("Motion sensor triggered");
        result.Axis.Should().Be(1);
        result.FloatValue.Should().Be(0.75f);
    }

    [Fact]
    public void ParseMotionPacket_WithInvalidJsonPayload_ShouldReturnNull()
    {
        // Arrange
        var invalidPayload = CreateInvalidTestPayload();
        var payloadBytes = CreateTestPacketPayload(invalidPayload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().BeNull();
    }

    [Fact]
    public void ParseMotionPacket_WithEmptyPayload_ShouldReturnNull()
    {
        // Arrange
        var emptyPayload = new byte[0];

        // Act
        var result = _motionCaptureService.ParseMotionPacket(emptyPayload);

        // Assert
        result.Should().BeNull();
    }

    [Fact]
    public void ParseMotionPacket_WithNullPayload_ShouldReturnNull()
    {
        // Arrange
        byte[]? nullPayload = null;

        // Act
        var result = _motionCaptureService.ParseMotionPacket(nullPayload);

        // Assert
        result.Should().BeNull();
    }

    [Fact]
    public void ParseMotionPacket_WithPartialJsonPayload_ShouldParseAvailableFields()
    {
        // Arrange
        var partialPayload = """{"type": false, "opcode": "PARTIAL_DATA"}""";
        var payloadBytes = CreateTestPacketPayload(partialPayload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeFalse();
        result.OpCode.Should().Be("PARTIAL_DATA");
        result.OpCodeDescription.Should().BeEmpty(); // Default value
        result.Axis.Should().Be(0); // Default value
        result.FloatValue.Should().Be(0.0f); // Default value
    }

    [Fact]
    public void ParseMotionPacket_WithDifferentDataTypes_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "TEST", "opcodedescription": "Test Description", "axis": 42, "floatvalue": -123.456}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("TEST");
        result.OpCodeDescription.Should().Be("Test Description");
        result.Axis.Should().Be(42);
        result.FloatValue.Should().Be(-123.456f);
    }

    [Fact]
    public void ParseMotionPacket_WithCaseInsensitiveFieldNames_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"TYPE": true, "OPCODE": "CASE_TEST", "OPCODEDESCRIPTION": "Case Test", "AXIS": 5, "FLOATVALUE": 99.9}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("CASE_TEST");
        result.OpCodeDescription.Should().Be("Case Test");
        result.Axis.Should().Be(5);
        result.FloatValue.Should().Be(99.9f);
    }

    [Fact]
    public void ParseMotionPacket_WithMalformedJson_ShouldReturnNull()
    {
        // Arrange
        var malformedJson = """{"type": true, "opcode": "TEST", "missing": "closing brace" """;
        var payloadBytes = CreateTestPacketPayload(malformedJson);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().BeNull();
    }

    [Fact]
    public void ParseMotionPacket_WithNonJsonPayload_ShouldReturnNull()
    {
        // Arrange
        var nonJsonPayload = "This is not JSON at all";
        var payloadBytes = CreateTestPacketPayload(nonJsonPayload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().BeNull();
    }

    [Fact]
    public void ParseMotionPacket_WithSpecialCharactersInStrings_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "SPECIAL_CHARS", "opcodedescription": "Test with \"quotes\" and \n newlines", "axis": 0, "floatvalue": 0.0}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.OpCode.Should().Be("SPECIAL_CHARS");
        result.OpCodeDescription.Should().Be("Test with \"quotes\" and \n newlines");
    }

    [Fact]
    public void ParseMotionPacket_WithNumericStringValues_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": "true", "opcode": "123", "opcodedescription": "456", "axis": "7", "floatvalue": "8.9"}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue(); // String "true" should be parsed as boolean true
        result.OpCode.Should().Be("123");
        result.OpCodeDescription.Should().Be("456");
        result.Axis.Should().Be(7);
        result.FloatValue.Should().Be(8.9f);
    }

    [Fact]
    public void ParseMotionPacket_WithVeryLargeValues_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "LARGE_VALUES", "opcodedescription": "Test with large values", "axis": 2147483647, "floatvalue": 3.402823E+38}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Axis.Should().Be(int.MaxValue);
        result.FloatValue.Should().Be(float.MaxValue);
    }

    [Fact]
    public void ParseMotionPacket_WithNegativeValues_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": false, "opcode": "NEGATIVE", "opcodedescription": "Negative values test", "axis": -42, "floatvalue": -123.456}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeFalse();
        result.Axis.Should().Be(-42);
        result.FloatValue.Should().Be(-123.456f);
    }

    [Fact]
    public void ParseMotionPacket_WithZeroValues_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": false, "opcode": "ZERO", "opcodedescription": "Zero values test", "axis": 0, "floatvalue": 0.0}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeFalse();
        result.Axis.Should().Be(0);
        result.FloatValue.Should().Be(0.0f);
    }

    [Fact]
    public void ParseMotionPacket_WithUnicodeCharacters_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "UNICODE", "opcodedescription": "Test with unicode: 🚀🌟🎯", "axis": 1, "floatvalue": 1.0}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.OpCode.Should().Be("UNICODE");
        result.OpCodeDescription.Should().Be("Test with unicode: 🚀🌟🎯");
    }

    [Fact]
    public void ParseMotionPacket_WithVeryLongStrings_ShouldParseCorrectly()
    {
        // Arrange
        var longString = new string('A', 1000);
        var payload = $"""{{"type": true, "opcode": "{longString}", "opcodedescription": "{longString}", "axis": 1, "floatvalue": 1.0}}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.OpCode.Should().Be(longString);
        result.OpCodeDescription.Should().Be(longString);
    }

    [Fact]
    public void ParseMotionPacket_WithScientificNotation_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "SCIENTIFIC", "opcodedescription": "Scientific notation test", "axis": 1, "floatvalue": 1.23e-4}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.FloatValue.Should().Be(1.23e-4f);
    }

    [Fact]
    public void ParseMotionPacket_WithExtraFields_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": true, "opcode": "EXTRA_FIELDS", "opcodedescription": "Extra fields test", "axis": 1, "floatvalue": 1.0, "extraField1": "value1", "extraField2": 42}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue();
        result.OpCode.Should().Be("EXTRA_FIELDS");
        result.OpCodeDescription.Should().Be("Extra fields test");
        result.Axis.Should().Be(1);
        result.FloatValue.Should().Be(1.0f);
    }

    [Fact]
    public void ParseMotionPacket_WithNullValues_ShouldUseDefaults()
    {
        // Arrange
        var payload = """{"type": null, "opcode": null, "opcodedescription": null, "axis": null, "floatvalue": null}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeFalse(); // Default value
        result.OpCode.Should().BeEmpty(); // Default value
        result.OpCodeDescription.Should().BeEmpty(); // Default value
        result.Axis.Should().Be(0); // Default value
        result.FloatValue.Should().Be(0.0f); // Default value
    }

    [Fact]
    public void ParseMotionPacket_WithMixedDataTypes_ShouldParseCorrectly()
    {
        // Arrange
        var payload = """{"type": "true", "opcode": 123, "opcodedescription": true, "axis": "42", "floatvalue": "3.14"}""";
        var payloadBytes = CreateTestPacketPayload(payload);

        // Act
        var result = _motionCaptureService.ParseMotionPacket(payloadBytes);

        // Assert
        result.Should().NotBeNull();
        result!.Type.Should().BeTrue(); // String "true" parsed as boolean
        result.OpCode.Should().Be("123"); // Number converted to string
        result.OpCodeDescription.Should().Be("True"); // Boolean converted to string
        result.Axis.Should().Be(42); // String "42" parsed as int
        result.FloatValue.Should().Be(3.14f); // String "3.14" parsed as float
    }
}
