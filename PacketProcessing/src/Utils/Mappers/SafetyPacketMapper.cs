using PacketProcessing.DTOs.Packet;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Utils.Mappers;

/// <summary>
/// Mapper for converting between SafetyPacketEntity and SafetyPacketDto
/// </summary>
public sealed class SafetyPacketMapper : IMapper<SafetyPacketDto, SafetyPacketEntity>
{
    /// <summary>
    /// Maps a SafetyPacketEntity to a SafetyPacketDto
    /// </summary>
    /// <param name="entity">The entity to map</param>
    /// <returns>The mapped DTO</returns>
    public static SafetyPacketDto ToDto(SafetyPacketEntity entity)
    {
        ArgumentNullException.ThrowIfNull(entity);

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
        ArgumentNullException.ThrowIfNull(dto);

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
}
