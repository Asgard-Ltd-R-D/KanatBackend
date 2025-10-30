using PacketProcessing.DTOs.Range;
using PacketProcessing.DTOs.Conf;
using PacketProcessing.Entities.Range;
using static PacketProcessing.DTOs.Range.RangeDto;

namespace PacketProcessing.Utils.Mappers;

/// <summary>
/// Mapper for converting between RangeEntity and RangeDto
/// </summary>
public sealed class RangeMapper : IMapper<RangeDto, RangeEntity>
{
    /// <summary>
    /// Maps a RangeEntity to a RangeDto
    /// </summary>
    /// <param name="entity">The entity to map</param>
    /// <returns>The mapped DTO</returns>
    public static RangeDto ToDto(RangeEntity entity)
    {
        ArgumentNullException.ThrowIfNull(entity);

        return new RangeDto
        {
            Id = entity.Id,
            Timestamp = entity.Timestamp,
            StartTime = entity.StartTime,
            EndTime = entity.EndTime,
            Description = entity.Description,
        };
    }

    /// <summary>
    /// Maps a RangeDto to a RangeEntity
    /// </summary>
    /// <param name="dto">The DTO to map</param>
    /// <returns>The mapped entity</returns>
    public static RangeEntity ToEntity(RangeDto dto)
    {
        ArgumentNullException.ThrowIfNull(dto);

        return new RangeEntity
        {
            Id = dto.Id,
            Timestamp = dto.Timestamp,
            StartTime = dto.StartTime,
            EndTime = dto.EndTime,
            Description = dto.Description
        };
    }
}
