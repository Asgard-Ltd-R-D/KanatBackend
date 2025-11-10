namespace PacketProcessing.DTOs.Conf;

public record struct EndpointSpecification(string? IP = null, int? Port = null);