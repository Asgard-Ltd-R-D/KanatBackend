using PacketProcessing.DTOs.Packet;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Utils.Mappers;

/// <summary>
/// Mapper for converting between OnVIFPacketEntity and OnVIFPacketDto
/// </summary>
public sealed class OnVIFPacketMapper : IMapper<OnVIFPacketDto, OnVIFPacketEntity>
{
    /// <summary>
    /// Maps an OnVIFPacketEntity to an OnVIFPacketDto
    /// </summary>
    /// <param name="entity">The entity to map</param>
    /// <returns>The mapped DTO</returns>
    public static OnVIFPacketDto ToDto(OnVIFPacketEntity entity)
    {
        ArgumentNullException.ThrowIfNull(entity);

        return new OnVIFPacketDto
        {
            Id = entity.Id,
            Timestamp = entity.Timestamp,
            Type = entity.Type,
            Description = entity.Description,
            Zoom = entity.Zoom,
            Measurement = entity.Measurement
        };
    }

    /// <summary>
    /// Maps an OnVIFPacketDto to an OnVIFPacketEntity
    /// </summary>
    /// <param name="dto">The DTO to map</param>
    /// <returns>The mapped entity</returns>
    public static OnVIFPacketEntity ToEntity(OnVIFPacketDto dto)
    {
        ArgumentNullException.ThrowIfNull(dto);

        return new OnVIFPacketEntity
        {
            Id = dto.Id,
            Timestamp = dto.Timestamp,
            Type = dto.Type,
            Description = dto.Description,
            Zoom = dto.Zoom,
            Measurement = dto.Measurement
        };
    }
}
