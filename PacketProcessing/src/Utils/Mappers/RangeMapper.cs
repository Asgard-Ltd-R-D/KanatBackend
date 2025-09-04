using PacketProcessing.DTOs.Range;
using PacketProcessing.Entities.Range;

namespace PacketProcessing.Utils.Mappers;

/// <summary>
/// Mapper for converting between RangeEntity and RangeDto
/// </summary>
public static class RangeMapper
{
    /// <summary>
    /// Maps a RangeEntity to a RangeDto
    /// </summary>
    /// <param name="entity">The entity to map</param>
    /// <returns>The mapped DTO</returns>
    public static RangeDto ToDto(RangeEntity entity)
    {
        if (entity == null)
            throw new ArgumentNullException(nameof(entity));

        return new RangeDto
        {
            Id = entity.Id,
            Timestamp = entity.Timestamp,
            Start = entity.Start,
            End = entity.End,
            Description = entity.Description
        };
    }

    /// <summary>
    /// Maps a RangeDto to a RangeEntity
    /// </summary>
    /// <param name="dto">The DTO to map</param>
    /// <returns>The mapped entity</returns>
    public static RangeEntity ToEntity(RangeDto dto)
    {
        if (dto == null)
            throw new ArgumentNullException(nameof(dto));

        return new RangeEntity
        {
            Id = dto.Id,
            Timestamp = dto.Timestamp,
            Start = dto.Start,
            End = dto.End,
            Description = dto.Description
        };
    }

    /// <summary>
    /// Maps a collection of RangeEntity to a collection of RangeDto
    /// </summary>
    /// <param name="entities">The entities to map</param>
    /// <returns>The mapped DTOs</returns>
    public static IEnumerable<RangeDto> ToDtoCollection(IEnumerable<RangeEntity> entities)
    {
        if (entities == null)
            throw new ArgumentNullException(nameof(entities));

        return entities.Select(ToDto);
    }

    /// <summary>
    /// Maps a collection of RangeDto to a collection of RangeEntity
    /// </summary>
    /// <param name="dtos">The DTOs to map</param>
    /// <returns>The mapped entities</returns>
    public static IEnumerable<RangeEntity> ToEntityCollection(IEnumerable<RangeDto> dtos)
    {
        if (dtos == null)
            throw new ArgumentNullException(nameof(dtos));

        return dtos.Select(ToEntity);
    }
}
