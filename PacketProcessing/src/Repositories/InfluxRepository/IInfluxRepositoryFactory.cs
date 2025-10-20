using Microsoft.Extensions.DependencyInjection;
using PacketProcessing.Entities;
using PacketProcessing.Repositories.InfluxRepository;

namespace PacketProcessing.Repositories.InfluxRepository;

public interface IInfluxRepositoryFactory
{
    IInfluxRepository<T> Get<T>() where T : BasePacketEntity;
}

public sealed class InfluxRepositoryFactory : IInfluxRepositoryFactory
{
    private readonly IServiceProvider _sp;
    public InfluxRepositoryFactory(IServiceProvider sp) => _sp = sp;
    public IInfluxRepository<T> Get<T>() where T : BasePacketEntity
        => _sp.GetRequiredService<IInfluxRepository<T>>();
}
