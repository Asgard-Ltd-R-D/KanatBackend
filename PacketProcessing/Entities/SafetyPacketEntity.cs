using System.ComponentModel.DataAnnotations;

namespace PacketProcessing.Entities;

public class SafetyPacketEntity
{
    [Key]
    public Guid Id { get; set; } = Guid.NewGuid();
    public bool Type { get; set; }
    public string OpCode { get; set; }
    public string OpCodeDescription { get; set; }
    public string State { get; set; }
    public ulong Timestamp { get; set; }
}