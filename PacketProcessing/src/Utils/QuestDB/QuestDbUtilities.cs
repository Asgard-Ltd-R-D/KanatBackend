using PacketProcessing.Entities;
using PacketProcessing.Entities.Packet;
using Npgsql;

namespace PacketProcessing.Utils.QuestDB;

/// <summary>
/// Utility methods for QuestDB operations
/// </summary>
public static class QuestDbUtilities
{
    /// <summary>
    /// Gets the table name for the specified entity type
    /// </summary>
    /// <typeparam name="T">The type of packet entity (must inherit from BasePacketEntity)</typeparam>
    /// <returns>The table name</returns>
    public static string GetTableName<T>() where T : BasePacketEntity
    {
        // Create a temporary instance to get the table name
        var tempEntity = Activator.CreateInstance<T>();
        return tempEntity.TableName;
    }
    
    /// <summary>
    /// Maps a QuestDB reader row to an entity
    /// </summary>
    /// <typeparam name="T">The type of packet entity (must inherit from BasePacketEntity)</typeparam>
    /// <param name="reader">The QuestDB reader</param>
    /// <returns>The mapped entity</returns>
    public static T MapReaderToEntity<T>(NpgsqlDataReader reader) where T : BasePacketEntity
    {
        // This is a simplified mapping - you might want to implement a more robust mapper
        var entity = Activator.CreateInstance<T>();
        
        // Map common properties
        entity.Id = reader.GetGuid(reader.GetOrdinal("id"));
        entity.Timestamp = reader.GetDateTime(reader.GetOrdinal("timestamp"));
        
        // Map specific properties based on entity type
        if (typeof(T) == typeof(MotionPacketEntity))
        {
            var motionEntity = entity as MotionPacketEntity;
            if (motionEntity != null)
            {
                motionEntity.Type = reader.GetBoolean(reader.GetOrdinal("type"));
                motionEntity.OpCode = reader.GetString(reader.GetOrdinal("opCode"));
                motionEntity.OpCodeDescription = reader.GetString(reader.GetOrdinal("opCodeDescription"));
                motionEntity.Axis = reader.GetInt32(reader.GetOrdinal("axis"));
                var floatValueOrdinal = reader.GetOrdinal("floatValue");
                motionEntity.FloatValue = reader.IsDBNull(floatValueOrdinal) ? null : reader.GetFloat(floatValueOrdinal);
            }
        }
        else if (typeof(T) == typeof(OnVIFPacketEntity))
        {
            var onvifEntity = entity as OnVIFPacketEntity;
            if (onvifEntity != null)
            {
                onvifEntity.Type = reader.GetBoolean(reader.GetOrdinal("type"));
                onvifEntity.Description = reader.GetString(reader.GetOrdinal("description"));
                var zoomOrdinal = reader.GetOrdinal("zoom");
                onvifEntity.Zoom = reader.IsDBNull(zoomOrdinal) ? null : reader.GetFloat(zoomOrdinal);
                onvifEntity.Measurement = reader.GetFloat(reader.GetOrdinal("measurement"));
            }
        }
        else if (typeof(T) == typeof(SafetyPacketEntity))
        {
            var safetyEntity = entity as SafetyPacketEntity;
            if (safetyEntity != null)
            {
                safetyEntity.Type = reader.GetBoolean(reader.GetOrdinal("type"));
                safetyEntity.OpCode = reader.GetString(reader.GetOrdinal("opCode"));
                safetyEntity.OpCodeDescription = reader.GetString(reader.GetOrdinal("opCodeDescription"));
                safetyEntity.State = reader.GetString(reader.GetOrdinal("state"));
            }
        }
        
        return entity;
    }
}
