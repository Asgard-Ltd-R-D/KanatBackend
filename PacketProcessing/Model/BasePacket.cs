namespace PacketProcessing.Model;

public class BasePacket
{
    public Guid Id { get; set; } = Guid.NewGuid();
}