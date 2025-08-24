using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using PacketProcessing.Entities;

namespace PacketProcessing.Context.Config;

public class OnVifPacketConfig : IEntityTypeConfiguration<OnVIFPacketEntity>
{
    public void Configure(EntityTypeBuilder<OnVIFPacketEntity> b)
    {
        b.ToTable("onvif_packets");                  
        b.HasKey(x => x.Id);

        b.Property(x => x.Id)
            .HasColumnName("id")
            .HasMaxLength(128)
            .IsRequired();
        
        b.Property(x => x.Description)
            .HasColumnName("description")
            .HasMaxLength(128)
            .IsRequired();
        
        b.Property(x => x.Zoom)
            .HasColumnName("zoom")
            .HasMaxLength(128)
            .IsRequired();

        b.Property(x => x.Measurement)
            .HasColumnName("measurement")
            .IsRequired();
        
        b.Property(x => x.Timestamp)
            .HasColumnName("timestamp")
            .HasColumnType("timestamp with time zone")
            .IsRequired();

        b.HasIndex(x => new { x.Id, x.Timestamp })
            .HasDatabaseName("ix_motion_packets_sensor_ts");    }
}