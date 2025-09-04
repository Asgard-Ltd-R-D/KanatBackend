using PacketProcessing.DTOs.Packet;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Utils.Mappers;

/// <summary>
/// Mapper for converting between SafetyPacketEntity and SafetyPacketDto
/// </summary>
public static class SafetyPacketMapper
{
    /// <summary>
    /// Maps a SafetyPacketEntity to a SafetyPacketDto
    /// </summary>
    /// <param name="entity">The entity to map</param>
    /// <returns>The mapped DTO</returns>
    public static SafetyPacketDto ToDto(SafetyPacketEntity entity)
    {
        if (entity == null)
            throw new ArgumentNullException(nameof(entity));

        return new SafetyPacketDto
        {
            Id = entity.Id,
            Timestamp = entity.Timestamp,
            Type = entity.Type,
            OpCode = entity.OpCode,
            OpCodeDescription = entity.OpCodeDescription,
            State = entity.State
        };
    }

    /// <summary>
    /// Maps a SafetyPacketDto to a SafetyPacketEntity
    /// </summary>
    /// <param name="dto">The DTO to map</param>
    /// <returns>The mapped entity</returns>
    public static SafetyPacketEntity ToEntity(SafetyPacketDto dto)
    {
        if (dto == null)
            throw new ArgumentNullException(nameof(dto));

        return new SafetyPacketEntity
        {
            Id = dto.Id,
            Timestamp = dto.Timestamp,
            Type = dto.Type,
            OpCode = dto.OpCode,
            OpCodeDescription = dto.OpCodeDescription,
            State = dto.State
        };
    }

    /// <summary>
    /// Maps a collection of SafetyPacketEntity to a collection of SafetyPacketDto
    /// </summary>
    /// <param name="entities">The entities to map</param>
    /// <returns>The mapped DTOs</returns>
    public static IEnumerable<SafetyPacketDto> ToDtoCollection(IEnumerable<SafetyPacketEntity> entities)
    {
        if (entities == null)
            throw new ArgumentNullException(nameof(entities));

        return entities.Select(ToDto);
    }

    /// <summary>
    /// Maps a collection of SafetyPacketDto to a collection of SafetyPacketEntity
    /// </summary>
    /// <param name="dtos">The DTOs to map</param>
    /// <returns>The mapped entities</returns>
    public static IEnumerable<SafetyPacketEntity> ToEntityCollection(IEnumerable<SafetyPacketDto> dtos)
    {
        if (dtos == null)
            throw new ArgumentNullException(nameof(dtos));

        return dtos.Select(ToEntity);
    }
}
