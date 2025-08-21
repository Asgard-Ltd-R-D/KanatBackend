using System.ComponentModel.DataAnnotations;

namespace PacketProcessing.Entities;

public class SafetyPacketEntity
{
    [Key]
    public Guid Id { get; set; } = Guid.NewGuid();
    public required bool Type { get; set; }
    public required string OpCode { get; set; }
    public required string OpCodeDescription { get; set; }
    public required string State { get; set; }
    public required ulong Timestamp { get; set; }
}