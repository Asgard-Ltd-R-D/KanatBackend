using PacketProcessing.DTOs.Range;
using PacketProcessing.Entities.Range;

namespace PacketProcessing.Utils.Mappers;

/// <summary>
/// Mapper for converting between TargetEntity and TargetDto
/// </summary>
public static class TargetMapper
{
    /// <summary>
    /// Maps a TargetEntity to a TargetDto
    /// </summary>
    /// <param name="entity">The entity to map</param>
    /// <returns>The mapped DTO</returns>
    public static TargetDto ToDto(TargetEntity entity)
    {
        if (entity == null)
            throw new ArgumentNullException(nameof(entity));

        return new TargetDto
        {
            Id = entity.Id,
            Timestamp = entity.Timestamp,
            PosX = entity.PosX,
            PosY = entity.PosY,
            CenterX = entity.CenterX,
            CenterY = entity.CenterY
        };
    }

    /// <summary>
    /// Maps a TargetDto to a TargetEntity
    /// </summary>
    /// <param name="dto">The DTO to map</param>
    /// <returns>The mapped entity</returns>
    public static TargetEntity ToEntity(TargetDto dto)
    {
        if (dto == null)
            throw new ArgumentNullException(nameof(dto));

        return new TargetEntity
        {
            Id = dto.Id,
            Timestamp = dto.Timestamp,
            PosX = dto.PosX,
            PosY = dto.PosY,
            CenterX = dto.CenterX,
            CenterY = dto.CenterY
        };
    }

    /// <summary>
    /// Maps a collection of TargetEntity to a collection of TargetDto
    /// </summary>
    /// <param name="entities">The entities to map</param>
    /// <returns>The mapped DTOs</returns>
    public static IEnumerable<TargetDto> ToDtoCollection(IEnumerable<TargetEntity> entities)
    {
        if (entities == null)
            throw new ArgumentNullException(nameof(entities));

        return entities.Select(ToDto);
    }

    /// <summary>
    /// Maps a collection of TargetDto to a collection of TargetEntity
    /// </summary>
    /// <param name="dtos">The DTOs to map</param>
    /// <returns>The mapped entities</returns>
    public static IEnumerable<TargetEntity> ToEntityCollection(IEnumerable<TargetDto> dtos)
    {
        if (dtos == null)
            throw new ArgumentNullException(nameof(dtos));

        return dtos.Select(ToEntity);
    }
}
