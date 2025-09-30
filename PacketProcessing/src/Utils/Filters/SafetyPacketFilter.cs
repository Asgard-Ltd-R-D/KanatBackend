using PacketProcessing.DTOs.Data;
using PacketProcessing.Entities.Packet;
using System.Reflection;

namespace PacketProcessing.Utils.Filters;

public static class SafetyPacketFilter
{
    public static async Task<IEnumerable<PlainDataDto>> FilterAsync(IEnumerable<SafetyPacketEntity> items, IReadOnlyDictionary<string, object>? filters)
    {
        // Use Task.Run to run the filtering operation asynchronously
        return await Task.Run(() =>
        {
            if (filters is null) return items.Select(item => new PlainDataDto
            {
                Timestamp = item.Timestamp,
                Value = item.OpCode?.GetHashCode() ?? 0
            });

            var filteredItems = items.Where(item => 
            {
                return filters.All(filter => 
                {
                    var property = typeof(SafetyPacketEntity).GetProperty(filter.Key, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                    if (property == null) return false;
                    
                    var value = property.GetValue(item);
                    return value?.Equals(filter.Value) == true;
                });
            });

            // Convert filtered entities to PlainDataDto
            return filteredItems.Select(item => new PlainDataDto
            {
                Timestamp = item.Timestamp,
                Value = item.OpCode?.GetHashCode() ?? 0
            });
        });
    }
}