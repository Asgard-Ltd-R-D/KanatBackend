using PacketProcessing.DTOs.Range;
using PacketProcessing.Entities.Range;

namespace PacketProcessing.Utils.Mappers;

/// <summary>
/// Mapper for converting between HitEntity and HitDto
/// </summary>
public static class HitMapper
{
    /// <summary>
    /// Maps a HitEntity to a HitDto
    /// </summary>
    /// <param name="entity">The entity to map</param>
    /// <returns>The mapped DTO</returns>
    public static HitDto ToDto(HitEntity entity)
    {
        if (entity == null)
            throw new ArgumentNullException(nameof(entity));

        return new HitDto
        {
            Id = entity.Id,
            Timestamp = entity.Timestamp,
            RangeToTarget = entity.RangeToTarget,
            PosX = entity.PosX,
            PosY = entity.PosY,
            CenterX = entity.CenterX,
            CenterY = entity.CenterY,
            TargetId = entity.TargetId,
            EventId = entity.EventId
        };
    }

    /// <summary>
    /// Maps a HitDto to a HitEntity
    /// </summary>
    /// <param name="dto">The DTO to map</param>
    /// <returns>The mapped entity</returns>
    public static HitEntity ToEntity(HitDto dto)
    {
        if (dto == null)
            throw new ArgumentNullException(nameof(dto));

        return new HitEntity
        {
            Id = dto.Id,
            Timestamp = dto.Timestamp,
            RangeToTarget = dto.RangeToTarget,
            PosX = dto.PosX,
            PosY = dto.PosY,
            CenterX = dto.CenterX,
            CenterY = dto.CenterY,
            TargetId = dto.TargetId,
            EventId = dto.EventId
        };
    }

    /// <summary>
    /// Maps a collection of HitEntity to a collection of HitDto
    /// </summary>
    /// <param name="entities">The entities to map</param>
    /// <returns>The mapped DTOs</returns>
    public static IEnumerable<HitDto> ToDtoCollection(IEnumerable<HitEntity> entities)
    {
        if (entities == null)
            throw new ArgumentNullException(nameof(entities));

        return entities.Select(ToDto);
    }

    /// <summary>
    /// Maps a collection of HitDto to a collection of HitEntity
    /// </summary>
    /// <param name="dtos">The DTOs to map</param>
    /// <returns>The mapped entities</returns>
    public static IEnumerable<HitEntity> ToEntityCollection(IEnumerable<HitDto> dtos)
    {
        if (dtos == null)
            throw new ArgumentNullException(nameof(dtos));

        return dtos.Select(ToEntity);
    }
}
