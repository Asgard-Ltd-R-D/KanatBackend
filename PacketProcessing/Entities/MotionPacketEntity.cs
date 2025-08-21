using System.ComponentModel.DataAnnotations;

namespace PacketProcessing.Entities;

public class MotionPacketEntity
{
    [Key]
    public Guid Id { get; set; } = Guid.NewGuid();
    public bool Type { get; set; }
    public string OpCode { get; set; }
    public string OpCodeDescription { get; set; }
    public int Axis { get; set; }
    public float? FloatValue { get; set; }
    public ulong Timestamp { get; set; }
}