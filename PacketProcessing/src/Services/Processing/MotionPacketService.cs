using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Threading.Channels;

namespace PacketProcessing.Services.Processing;

/// <summary>
/// Motion packet service for batch processing motion packets
/// </summary>
public class MotionPacketService : BasePacketService<MotionPacketEntity>
{
    public MotionPacketService(
        ILogger<MotionPacketService> logger,
        IPacketRepository<MotionPacketEntity> repository,
        Channel<MotionPacketEntity> channel,
        IConfiguration configuration)
        : base(logger, repository, channel, configuration)
    {
    }
}
