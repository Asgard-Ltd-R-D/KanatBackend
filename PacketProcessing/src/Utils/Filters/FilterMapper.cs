using PacketProcessing.DTOs.Data;
using PacketProcessing.Entities;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Utils.Filters;

public static class FilterMapper
{
    public static async Task<IEnumerable<PlainDataDto>?> MapAsync<T>(IEnumerable<T> items, IReadOnlyDictionary<string, object>? filters) where T : BasePacketEntity
    {
        return typeof(T) switch
        {
            var t when t == typeof(MotionPacketEntity) => await MotionPacketFilter.FilterAsync(items.Cast<MotionPacketEntity>(), filters),
            var t when t == typeof(SafetyPacketEntity) => await SafetyPacketFilter.FilterAsync(items.Cast<SafetyPacketEntity>(), filters),
            var t when t == typeof(OnVIFPacketEntity) => await OnVifPacketFilter.FilterAsync(items.Cast<OnVIFPacketEntity>(), filters),
            _ => null
        };    
    }
}