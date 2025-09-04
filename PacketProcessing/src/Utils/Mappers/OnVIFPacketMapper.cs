using PacketProcessing.DTOs.Packet;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Utils.Mappers;

/// <summary>
/// Mapper for converting between OnVIFPacketEntity and OnVIFPacketDto
/// </summary>
public static class OnVIFPacketMapper
{
    /// <summary>
    /// Maps an OnVIFPacketEntity to an OnVIFPacketDto
    /// </summary>
    /// <param name="entity">The entity to map</param>
    /// <returns>The mapped DTO</returns>
    public static OnVIFPacketDto ToDto(OnVIFPacketEntity entity)
    {
        if (entity == null)
            throw new ArgumentNullException(nameof(entity));

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
        if (dto == null)
            throw new ArgumentNullException(nameof(dto));

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

    /// <summary>
    /// Maps a collection of OnVIFPacketEntity to a collection of OnVIFPacketDto
    /// </summary>
    /// <param name="entities">The entities to map</param>
    /// <returns>The mapped DTOs</returns>
    public static IEnumerable<OnVIFPacketDto> ToDtoCollection(IEnumerable<OnVIFPacketEntity> entities)
    {
        if (entities == null)
            throw new ArgumentNullException(nameof(entities));

        return entities.Select(ToDto);
    }

    /// <summary>
    /// Maps a collection of OnVIFPacketDto to a collection of OnVIFPacketEntity
    /// </summary>
    /// <param name="dtos">The DTOs to map</param>
    /// <returns>The mapped entities</returns>
    public static IEnumerable<OnVIFPacketEntity> ToEntityCollection(IEnumerable<OnVIFPacketDto> dtos)
    {
        if (dtos == null)
            throw new ArgumentNullException(nameof(dtos));

        return dtos.Select(ToEntity);
    }
}
