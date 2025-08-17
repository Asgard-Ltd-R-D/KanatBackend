using PacketProcessing.Models;

namespace PacketProcessing.Interfaces;

public interface IPacketStorage
{
    Task StorePacketAsync(PacketData packet);
    Task StorePacketsBatchAsync(IEnumerable<PacketData> packets);
    Task<IEnumerable<PacketData>> GetPacketsAsync(DateTime from, DateTime to, int limit = 1000);
    Task<long> GetPacketCountAsync(DateTime from, DateTime to);
}
