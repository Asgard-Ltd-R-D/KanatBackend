using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Repositories;

public interface IRepository<T> : IILPRepository<T> where T : class 
{ 
    Task<IEnumerable<T>> GetAllPacketsAsync();
    Task DeleteAllPacketsAsync();
    Task<IEnumerable<T>> GetPaginatedPacketsBetweenTimestampsAsync(long startTimestamp, long endTimestamp, OrderBy orderBy = OrderBy.Asc, int page = 1, int pageSize = 1_000);
}