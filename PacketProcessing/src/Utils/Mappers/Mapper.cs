namespace PacketProcessing.Utils.Mappers;

/// <summary>
/// Mapper interface for converting between DTO and Entity
/// </summary>
/// <typeparam name="D">DTO type</typeparam>
/// <typeparam name="E">Entity type</typeparam>
public interface IMapper<D, E> where D : class where E : class
{
   static abstract D ToDto(E entity);
   static abstract E ToEntity(D dto);
}