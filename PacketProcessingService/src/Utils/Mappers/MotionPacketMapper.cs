using PacketProcessing.DTOs.Packet;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Utils.Mappers;

/// <summary>
/// Mapper for converting between MotionPacketEntity and MotionPacketDto
/// </summary>
public sealed class MotionPacketMapper : IMapper<MotionPacketDto, MotionPacketEntity>
{
    /// <summary>
    /// Maps a MotionPacketEntity to a MotionPacketDto
    /// </summary>
    /// <param name="entity">The entity to map</param>
    /// <returns>The mapped DTO</returns>
    public static MotionPacketDto ToDto(MotionPacketEntity entity)
    {
        ArgumentNullException.ThrowIfNull(entity);

        return new MotionPacketDto
        {
            Id = entity.Id,
            Timestamp = entity.Timestamp,
            IsCmd = entity.IsCmd,
            OpCode = entity.OpCode,
            Description = entity.Description,
            Axis = entity.Axis,
            Value = entity.Value
        };
    }

    /// <summary>
    /// Maps a MotionPacketDto to a MotionPacketEntity
    /// </summary>
    /// <param name="dto">The DTO to map</param>
    /// <returns>The mapped entity</returns>
    public static MotionPacketEntity ToEntity(MotionPacketDto dto)
    {
        ArgumentNullException.ThrowIfNull(dto);

        return new MotionPacketEntity
        {
            Id = dto.Id,
            Timestamp = dto.Timestamp,
            IsCmd = dto.IsCmd,
            OpCode = dto.OpCode,
            Description = dto.Description,
            Axis = dto.Axis,
            Value = dto.Value
        };
    }
}
