using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PacketProcessing.Entities;

namespace PacketProcessing.Context.Config;

public class SafetyPacketConfig : IEntityTypeConfiguration<SafetyPacketEntity>
{
    public void Configure(EntityTypeBuilder<SafetyPacketEntity> b)
    {
        b.ToTable("safety_packets");
        b.HasKey(x => x.Id);

        b.Property(x => x.Id)
            .HasColumnName("id")
            .HasMaxLength(128)
            .IsRequired();

        b.Property(x => x.Type)
            .HasColumnName("type")
            .HasMaxLength(128)
            .IsRequired();

        b.Property(x => x.OpCode)
            .HasColumnName("opCode")
            .IsRequired();
        
        b.Property(x => x.OpCodeDescription)
            .HasColumnName("opCodeDescription")
            .IsRequired();

        b.Property(x => x.Timestamp)
            .HasColumnName("timestamp")
            .HasColumnType("timestamp with time zone")
            .IsRequired();

        b.HasIndex(x => new { x.Id, x.Timestamp })
            .HasDatabaseName("ix_safety_packets_sensor_ts");
    }
}