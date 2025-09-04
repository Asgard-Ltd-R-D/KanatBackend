using PacketProcessing.DTOs.Packet;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Utils.Mappers;

/// <summary>
/// Mapper for converting between MotionPacketEntity and MotionPacketDto
/// </summary>
public static class MotionPacketMapper
{
    /// <summary>
    /// Maps a MotionPacketEntity to a MotionPacketDto
    /// </summary>
    /// <param name="entity">The entity to map</param>
    /// <returns>The mapped DTO</returns>
    public static MotionPacketDto ToDto(MotionPacketEntity entity)
    {
        if (entity == null)
            throw new ArgumentNullException(nameof(entity));

        return new MotionPacketDto
        {
            Id = entity.Id,
            Timestamp = entity.Timestamp,
            Type = entity.Type,
            OpCode = entity.OpCode,
            OpCodeDescription = entity.OpCodeDescription,
            Axis = entity.Axis,
            FloatValue = entity.FloatValue
        };
    }

    /// <summary>
    /// Maps a MotionPacketDto to a MotionPacketEntity
    /// </summary>
    /// <param name="dto">The DTO to map</param>
    /// <returns>The mapped entity</returns>
    public static MotionPacketEntity ToEntity(MotionPacketDto dto)
    {
        if (dto == null)
            throw new ArgumentNullException(nameof(dto));

        return new MotionPacketEntity
        {
            Id = dto.Id,
            Timestamp = dto.Timestamp,
            Type = dto.Type,
            OpCode = dto.OpCode,
            OpCodeDescription = dto.OpCodeDescription,
            Axis = dto.Axis,
            FloatValue = dto.FloatValue
        };
    }

    /// <summary>
    /// Maps a collection of MotionPacketEntity to a collection of MotionPacketDto
    /// </summary>
    /// <param name="entities">The entities to map</param>
    /// <returns>The mapped DTOs</returns>
    public static IEnumerable<MotionPacketDto> ToDtoCollection(IEnumerable<MotionPacketEntity> entities)
    {
        if (entities == null)
            throw new ArgumentNullException(nameof(entities));

        return entities.Select(ToDto);
    }

    /// <summary>
    /// Maps a collection of MotionPacketDto to a collection of MotionPacketEntity
    /// </summary>
    /// <param name="dtos">The DTOs to map</param>
    /// <returns>The mapped entities</returns>
    public static IEnumerable<MotionPacketEntity> ToEntityCollection(IEnumerable<MotionPacketDto> dtos)
    {
        if (dtos == null)
            throw new ArgumentNullException(nameof(dtos));

        return dtos.Select(ToEntity);
    }
}
