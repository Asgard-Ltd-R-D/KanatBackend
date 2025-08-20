namespace PacketProcessing.Model;

public abstract class BasePacket
{
    public Guid Id { get; set; } = Guid.NewGuid();
}