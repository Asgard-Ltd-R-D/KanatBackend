using PacketProcessing.DTOs.Range;
using PacketProcessing.Entities.Range;

namespace PacketProcessing.Utils.Mappers;

/// <summary>
/// Mapper for converting between EventEntity and EventDto
/// </summary>
public sealed class EventMapper : IMapper<EventDto, EventEntity>
{
    /// <summary>
    /// Maps an EventEntity to an EventDto
    /// </summary>
    /// <param name="entity">The entity to map</param>
    /// <returns>The mapped DTO</returns>
    public static EventDto ToDto(EventEntity entity)
    {
        ArgumentNullException.ThrowIfNull(entity);

        return new EventDto
        {
            Id = entity.Id,
            Timestamp = entity.Timestamp,
            Start = entity.Start,
            End = entity.End,
            RangeId = entity.RangeId
        };
    }

    /// </summary>
    /// <param name="dto">The DTO to map</param>
    /// <returns>The mapped entity</returns>
    public static EventEntity ToEntity(EventDto dto)
    {
        ArgumentNullException.ThrowIfNull(dto);

        return new EventEntity
        {
            Id = dto.Id,
            Timestamp = dto.Timestamp,
            Start = dto.Start,
            End = dto.End,
            RangeId = dto.RangeId
        };
    }
}
