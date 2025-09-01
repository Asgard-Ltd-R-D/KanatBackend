using PacketProcessing.Entities.Packet;
using PacketProcessing.Repositories;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using System.Threading.Channels;
using PacketProcessing.Services.Networking;

namespace PacketProcessing.Services.Processing;

/// <summary>
/// OnVIF packet service for batch processing OnVIF packets
/// </summary>
public sealed class OnVIFPacketService : BasePacketService<OnVIFPacketEntity>
{
    public OnVIFPacketService(
        ILogger<OnVIFPacketService> logger,
        IPacketRepository<OnVIFPacketEntity> repository,
        Channel<OnVIFPacketEntity> channel,
        OnVIFCaptureService captureService,
        IConfiguration configuration)
        : base(logger, repository, channel, captureService, configuration)
    {
    }
}
