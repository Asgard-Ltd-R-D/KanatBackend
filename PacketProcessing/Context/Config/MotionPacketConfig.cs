using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PacketProcessing.Entities;

namespace PacketProcessing.Context.Config;

public class MotionPacketConfig : IEntityTypeConfiguration<MotionPacketEntity>
{
    public void Configure(EntityTypeBuilder<MotionPacketEntity> b)
    {
        b.ToTable("motion_packets");                  
        b.HasKey(x => x.Id);

        b.Property(x => x.Id)
            .HasColumnName("id")
            .HasMaxLength(128)
            .IsRequired();
        
        b.Property(x => x.OpCode)
            .HasColumnName("opCode")
            .HasMaxLength(32)
            .IsRequired();
        
        b.Property(x => x.OpCodeDescription)
            .HasColumnName("opCodeDescription")
            .HasMaxLength(128)
            .IsRequired();

        b.Property(x => x.Axis)
            .HasColumnName("axis")
            .IsRequired();

        b.Property(x => x.FloatValue)
            .HasColumnName("floatValue");

        b.Property(x => x.Timestamp)
            .HasColumnName("timestamp")
            .HasColumnType("timestamp with time zone")
            .IsRequired();

        b.HasIndex(x => new { x.Id, x.Timestamp })
            .HasDatabaseName("ix_motion_packets_sensor_ts");
    }
}