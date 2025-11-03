namespace PacketProcessing.DTOs.Stream;

public class IntervalRequestDto
{
    public required string SubscriptionKey { get; set; }
    public required int IntervalMs { get; set; }
}