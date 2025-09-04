using PacketProcessing.DTOs.Range;
using PacketProcessing.Entities.Range;

namespace PacketProcessing.Utils.Mappers;

/// <summary>
/// Mapper for converting between EventEntity and EventDto
/// </summary>
public static class EventMapper
{
    /// <summary>
    /// Maps an EventEntity to an EventDto
    /// </summary>
    /// <param name="entity">The entity to map</param>
    /// <returns>The mapped DTO</returns>
    public static EventDto ToDto(EventEntity entity)
    {
        if (entity == null)
            throw new ArgumentNullException(nameof(entity));

        return new EventDto
        {
            Id = entity.Id,
            Timestamp = entity.Timestamp,
            Start = entity.Start,
            End = entity.End,
            RangeId = entity.RangeId
        };
    }

    /// <summary>
    /// Maps an EventDto to an EventEntity
    /// </summary>
    /// <param name="dto">The DTO to map</param>
    /// <returns>The mapped entity</returns>
    public static EventEntity ToEntity(EventDto dto)
    {
        if (dto == null)
            throw new ArgumentNullException(nameof(dto));

        return new EventEntity
        {
            Id = dto.Id,
            Timestamp = dto.Timestamp,
            Start = dto.Start,
            End = dto.End,
            RangeId = dto.RangeId
        };
    }

    /// <summary>
    /// Maps a collection of EventEntity to a collection of EventDto
    /// </summary>
    /// <param name="entities">The entities to map</param>
    /// <returns>The mapped DTOs</returns>
    public static IEnumerable<EventDto> ToDtoCollection(IEnumerable<EventEntity> entities)
    {
        if (entities == null)
            throw new ArgumentNullException(nameof(entities));

        return entities.Select(ToDto);
    }

    /// <summary>
    /// Maps a collection of EventDto to a collection of EventEntity
    /// </summary>
    /// <param name="dtos">The DTOs to map</param>
    /// <returns>The mapped entities</returns>
    public static IEnumerable<EventEntity> ToEntityCollection(IEnumerable<EventDto> dtos)
    {
        if (dtos == null)
            throw new ArgumentNullException(nameof(dtos));

        return dtos.Select(ToEntity);
    }
}
