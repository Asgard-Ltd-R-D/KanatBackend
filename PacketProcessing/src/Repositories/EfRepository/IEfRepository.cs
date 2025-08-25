using PacketProcessing.Entities;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Repositories.EfRepository;

public interface IEfRepository<T> where T : BaseEntity
{
    /// <summary>
    /// Adds a single entity to the database
    /// </summary>
    /// <param name="entity">The entity to add</param>
    /// <returns>The added entity with updated ID</returns>
    Task<T> AddAsync(T entity);
    
    /// <summary>
    /// Adds multiple entities to the database in a batch
    /// </summary>
    /// <param name="entities">The entities to add</param>
    /// <returns>The number of entities added</returns>
    Task<int> AddRangeAsync(IEnumerable<T> entities);
    
    /// <summary>
    /// Gets an entity by its ID
    /// </summary>
    /// <param name="id">The entity ID</param>
    /// <returns>The entity if found, null otherwise</returns>
    Task<T?> GetByIdAsync(Guid id);
    
    /// <summary>
    /// Updates an existing entity
    /// </summary>
    /// <param name="entity">The entity to update</param>
    /// <returns>The updated entity</returns>
    Task<T> UpdateAsync(T entity);
    
    /// <summary>
    /// Deletes an entity by its ID
    /// </summary>
    /// <param name="id">The entity ID to delete</param>
    /// <returns>True if the entity was deleted, false if not found</returns>
    Task<bool> DeleteAsync(Guid id);
}