using System.ComponentModel.DataAnnotations;

namespace PacketProcessing.Entities;

public class MotionPacketEntity
{
    [Key]
    public Guid Id { get; set; } = Guid.NewGuid();
    public bool Type { get; set; }
    public required string OpCode { get; set; }
    public required string OpCodeDescription { get; set; }
    public required int Axis { get; set; }
    public float? FloatValue { get; set; }
    public required ulong Timestamp { get; set; }
}