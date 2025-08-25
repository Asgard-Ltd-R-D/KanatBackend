using PacketProcessing.Entities;

namespace PacketProcessing.Utils.QuestDB;

public static class PacketRowMapper<T> where T : BasePacketEntity
{ 
    public static RowMap Map(T entity) => entity.ToRowMap();
}