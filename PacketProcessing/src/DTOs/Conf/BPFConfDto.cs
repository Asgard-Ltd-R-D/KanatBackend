namespace PacketProcessing.DTOs.Conf;

public class BPFConfDto
{
    public EndpointSpecification[]? Safety { get; set; } = [];
    public EndpointSpecification[]? Motion { get; set; } = [];
    public EndpointSpecification[]? OnVIF { get; set; } = [];
    public required string Device { get; set; } = string.Empty;
}