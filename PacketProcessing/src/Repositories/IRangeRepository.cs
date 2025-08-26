using PacketProcessing.Entities;
using PacketProcessing.Repositories.EfRepository;

namespace PacketProcessing.Repositories;

public interface IRangeRepository<T> : IEfRepository<T> where T : BaseEntity { }