namespace PacketProcessing.DTOs.Conf;

public class BPFConfDto
{
    public class SafetyConf
    {
        public EndpointSpecification? Sbe { get; set; } = null;
        public EndpointSpecification? Pbe { get; set; } = null;
    }

    public SafetyConf? Safety { get; set; } = null;
    public EndpointSpecification[]? Motion { get; set; } = [];
    public EndpointSpecification[]? OnVIF { get; set; } = [];
    public required string Device { get; set; } = string.Empty;
}