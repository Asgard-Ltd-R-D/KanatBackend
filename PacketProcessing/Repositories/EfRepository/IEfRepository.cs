using PacketProcessing.Entities;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Repositories.EfRepository;

public interface IEfRepository<T> where T : BasePacketEntity
{
    Task<IEnumerable<T>> GetAllPacketsAsync();
    
    Task DeleteAllPacketsAsync();
    
    Task<IEnumerable<T>> GetPaginatedPacketsBetweenTimestampsAsync(
        DateTime startTimestamp, DateTime endTimestamp, OrderBy orderBy = OrderBy.Asc, int page = 1, int pageSize = 1_000);
}