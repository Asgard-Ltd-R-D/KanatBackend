using Microsoft.Extensions.Logging;
using PacketProcessing.Context;
using PacketProcessing.Entities;
using PacketProcessing.Repositories.EfRepository;

namespace PacketProcessing.Repositories;

public class RangeRepository<T> : EfRepository<T>, IRangeRepository<T> where T : BaseEntity
{
    public RangeRepository(AppDbContext context, ILogger<EfRepository<T>> logger) : base(context, logger) { }
}