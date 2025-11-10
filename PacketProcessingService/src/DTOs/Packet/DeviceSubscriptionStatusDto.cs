namespace PacketProcessing.DTOs.Packet;

public class DeviceSubscriptionStatusDto
{
    public string DeviceName { get; set; } = string.Empty;
    public string Filter { get; set; } = string.Empty;
    public bool IsCapturing { get; set; } = false;
}
