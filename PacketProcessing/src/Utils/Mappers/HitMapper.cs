using PacketProcessing.DTOs.Range;
using PacketProcessing.Entities.Range;

namespace PacketProcessing.Utils.Mappers;

/// <summary>
/// Mapper for converting between HitEntity and HitDto
/// </summary>
public sealed class HitMapper : IMapper<HitDto, HitEntity>
{
    /// <summary>
    /// Maps a HitEntity to a HitDto
    /// </summary>
    /// <param name="entity">The entity to map</param>
    /// <returns>The mapped DTO</returns>
    public static HitDto ToDto(HitEntity entity)
    {
        ArgumentNullException.ThrowIfNull(entity);

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
        ArgumentNullException.ThrowIfNull(dto);

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
}
