using Microsoft.Extensions.DependencyInjection;
using PacketProcessing.Entities;

namespace PacketProcessing.Repositories.EfRepository;

public interface IEfRepositoryFactory
{
    IEfRepository<T> Get<T>() where T : BaseEntity;
}

public sealed class EfRepositoryFactory : IEfRepositoryFactory
{
    private readonly IServiceProvider _sp;
    public EfRepositoryFactory(IServiceProvider sp) => _sp = sp;
    public IEfRepository<T> Get<T>() where T : BaseEntity
        => _sp.GetRequiredService<IEfRepository<T>>();
}

