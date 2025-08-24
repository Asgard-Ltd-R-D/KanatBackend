using PacketProcessing.Entities;
using PacketProcessing.Repositories.EfRepository;
using PacketProcessing.Repositories.InfluxRepository;

namespace PacketProcessing.Repositories;

public interface IRepository<T> : IInfluxRepository<T>, IEfRepository<T>, IAsyncDisposable where T : BasePacketEntity { }