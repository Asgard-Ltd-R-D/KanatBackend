using PacketProcessing.Entities;
using PacketProcessing.Entities.Packet;
using QuestDB.Senders;
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
    
    /// <summary>
    /// Parses QuestDB raw response and maps it to entities
    /// </summary>
    public static IEnumerable<T> ParseQuestDbRawResponse<T>(string rawResponse) where T : BasePacketEntity
    {
        try
        {
            // QuestDB raw response is typically CSV format
            var lines = rawResponse.Split('\n', StringSplitOptions.RemoveEmptyEntries);
            if (lines.Length < 2) // Need at least header and one data row
            {
                return new List<T>();
            }
            
            var result = new List<T>();
            var headers = lines[0].Split(',');
            
            for (int i = 1; i < lines.Length; i++)
            {
                var values = lines[i].Split(',');
                if (values.Length == headers.Length)
                {
                    var entity = CreateEntityFromRawData<T>(headers, values);
                    if (entity != null)
                    {
                        result.Add(entity);
                    }
                }
            }
            
            return result;
        }
        catch (Exception)
        {
            // If parsing fails, return empty collection
            return new List<T>();
        }
    }
    
    /// <summary>
    /// Creates an entity from QuestDB raw data
    /// </summary>
    private static T CreateEntityFromRawData<T>(string[] headers, string[] values) where T : BasePacketEntity
    {
        try
        {
            var entity = Activator.CreateInstance<T>();
            
            for (int i = 0; i < headers.Length && i < values.Length; i++)
            {
                var header = headers[i].Trim();
                var value = values[i].Trim();
                
                switch (header.ToLower())
                {
                    case "id":
                        if (Guid.TryParse(value, out var id))
                            entity.Id = id;
                        break;
                    case "timestamp":
                        if (DateTime.TryParse(value, out var timestamp))
                            entity.Timestamp = timestamp;
                        break;
                    case "type":
                        if (bool.TryParse(value, out var type))
                        {
                            if (typeof(T) == typeof(MotionPacketEntity))
                                ((MotionPacketEntity)(object)entity).Type = type;
                            else if (typeof(T) == typeof(OnVIFPacketEntity))
                                ((OnVIFPacketEntity)(object)entity).Type = type;
                            else if (typeof(T) == typeof(SafetyPacketEntity))
                                ((SafetyPacketEntity)(object)entity).Type = type;
                        }
                        break;
                    case "opcode":
                        if (typeof(T) == typeof(MotionPacketEntity))
                            ((MotionPacketEntity)(object)entity).OpCode = value;
                        else if (typeof(T) == typeof(SafetyPacketEntity))
                            ((SafetyPacketEntity)(object)entity).OpCode = value;
                        break;
                    case "opcodedescription":
                        if (typeof(T) == typeof(MotionPacketEntity))
                            ((MotionPacketEntity)(object)entity).OpCodeDescription = value;
                        else if (typeof(T) == typeof(SafetyPacketEntity))
                            ((SafetyPacketEntity)(object)entity).OpCodeDescription = value;
                        break;
                    case "axis":
                        if (int.TryParse(value, out var axis) && typeof(T) == typeof(MotionPacketEntity))
                            ((MotionPacketEntity)(object)entity).Axis = axis;
                        break;
                    case "floatvalue":
                        if (float.TryParse(value, out var floatValue) && typeof(T) == typeof(MotionPacketEntity))
                            ((MotionPacketEntity)(object)entity).FloatValue = floatValue;
                        break;
                    case "description":
                        if (typeof(T) == typeof(OnVIFPacketEntity))
                            ((OnVIFPacketEntity)(object)entity).Description = value;
                        break;
                    case "zoom":
                        if (float.TryParse(value, out var zoom) && typeof(T) == typeof(OnVIFPacketEntity))
                            ((OnVIFPacketEntity)(object)entity).Zoom = zoom;
                        break;
                    case "measurement":
                        if (float.TryParse(value, out var measurement) && typeof(T) == typeof(OnVIFPacketEntity))
                            ((OnVIFPacketEntity)(object)entity).Measurement = measurement;
                        break;
                    case "state":
                        if (typeof(T) == typeof(SafetyPacketEntity))
                            ((SafetyPacketEntity)(object)entity).State = value;
                        break;
                }
            }
            
            return entity;
        }
        catch (Exception)
        {
            return default(T)!;
        }
    }
}

/// <summary>
/// Maps packet entities to QuestDB rows
/// </summary>
public static class PacketRowMapper<T> where T : BasePacketEntity
{ 
    public static RowMap Map(T entity) => entity.ToRowMap();
}

/// <summary>
/// Represents a QuestDB row mapping
/// </summary>
public sealed class RowMap
{
    public string Table { get; }
    public DateTime TimestampUtc { get; }
    private readonly Action<ISender> _apply;
    
    public RowMap(string table, DateTime timestampUtc, Action<ISender> apply)
    {
        Table = table ?? throw new ArgumentNullException(nameof(table));
        TimestampUtc = DateTime.SpecifyKind(timestampUtc, DateTimeKind.Utc);
        _apply = apply ?? throw new ArgumentNullException(nameof(apply));
    }
    
    public void Apply(ISender sender) => _apply(sender);
}
