using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Threading.Channels;

namespace PacketProcessing.Services.Processing;

/// <summary>
/// Safety packet service for batch processing safety packets
/// </summary>
public class SafetyPacketService : BasePacketService<SafetyPacketEntity>
{
    public SafetyPacketService(
        ILogger<SafetyPacketService> logger,
        IPacketRepository<SafetyPacketEntity> repository,
        Channel<SafetyPacketEntity> channel,
        IConfiguration configuration)
        : base(logger, repository, channel, configuration)
    {
    }
}
