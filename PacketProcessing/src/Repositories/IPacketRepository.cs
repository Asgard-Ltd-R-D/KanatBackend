using PacketProcessing.Entities;
using PacketProcessing.Repositories.InfluxRepository;

namespace PacketProcessing.Repositories;

/// <summary>
/// Generic repository interface for packet-specific operations
/// Provides specialized methods for handling different types of packet entities
/// Extends basic CRUD operations from EfRepository and includes InfluxDB operations
/// </summary>
/// <typeparam name="T">The type of packet entity (must inherit from BasePacketEntity)</typeparam>
public interface IPacketRepository<T> : IInfluxRepository<T> where T : BasePacketEntity { }