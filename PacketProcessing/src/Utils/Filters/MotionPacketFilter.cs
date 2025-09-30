using PacketProcessing.DTOs.Data;
using PacketProcessing.Entities.Packet;
using System.Reflection;

namespace PacketProcessing.Utils.Filters;

public static class MotionPacketFilter 
{
    public static async Task<IEnumerable<PlainDataDto>> FilterAsync(IEnumerable<MotionPacketEntity> items, IReadOnlyDictionary<string, object>? filters)
    {
        // Use Task.Run to run the filtering operation asynchronously
        return await Task.Run(() =>
        {
            if (filters is null) return items.Select(item => new PlainDataDto
            {
                Timestamp = item.Timestamp,
                Value = item.FloatValue ?? 0.0f
            });

            var filteredItems = items.Where(item => 
            {
                return filters.All(filter => 
                {
                    var property = typeof(MotionPacketEntity).GetProperty(filter.Key, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                    if (property == null) return false;
                    
                    var value = property.GetValue(item);
                    return value?.Equals(filter.Value) == true;
                });
            });

            // Convert filtered entities to PlainDataDto
            return filteredItems.Select(item => new PlainDataDto
            {
                Timestamp = item.Timestamp,
                Value = item.FloatValue ?? 0.0f
            });
        });
    }
}