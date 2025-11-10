using PacketProcessing.DTOs.Conf;

namespace PacketProcessing.DTOs.Range;

/// <summary>
/// Data Transfer Object for RangeEntity
/// </summary>
public class RangeDto
{
    public class RangeConfig
    {
        public BPFConfDto? BpfConfig { get; set; }
        public EndpointSpecification? MtxConfig { get; set; }
        public CameraConfDto[]? Cams { get; set; }
    }

    public Guid Id { get; set; }
    public DateTime Timestamp { get; set; }
    public string Description { get; set; } = string.Empty;
    public long StartTime { get; set; }
    public long EndTime { get; set; }
    public RangeConfig? Config { get; set; }
}
