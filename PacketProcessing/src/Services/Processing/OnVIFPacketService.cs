using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Threading.Channels;

namespace PacketProcessing.Services.Processing;

/// <summary>
/// OnVIF packet service for batch processing OnVIF packets
/// </summary>
public class OnVIFPacketService : BasePacketService<OnVIFPacketEntity>
{
    public OnVIFPacketService(
        ILogger<OnVIFPacketService> logger,
        IPacketRepository<OnVIFPacketEntity> repository,
        Channel<OnVIFPacketEntity> channel,
        IConfiguration configuration)
        : base(logger, repository, channel, configuration)
    {
    }
}
