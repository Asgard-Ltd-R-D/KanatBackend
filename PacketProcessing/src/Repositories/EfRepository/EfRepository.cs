using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using PacketProcessing.Context;
using PacketProcessing.Entities;
using PacketProcessing.Utils.Enums;

namespace PacketProcessing.Repositories.EfRepository;

public class EfRepository<T> : IEfRepository<T> where T : BaseEntity
{
    protected readonly PostgresDbContext _context;
    protected readonly ILogger<EfRepository<T>> _logger;
    
    public EfRepository(PostgresDbContext context, ILogger<EfRepository<T>> logger)
    {
        _context = context ?? throw new ArgumentNullException(nameof(context));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }
    
    /// <summary>
    /// Adds a single entity to the database
    /// </summary>
    /// <param name="entity">The entity to add</param>
    /// <returns>The added entity with updated ID</returns>
    public async Task<T> AddAsync(T entity)
    {
        try
        {
            _logger.LogDebug("Adding entity of type {EntityType} with ID {Id}", typeof(T).Name, entity.Id);
            
            var result = await _context.Set<T>().AddAsync(entity);
            await _context.SaveChangesAsync();
            
            _logger.LogDebug("Successfully added entity of type {EntityType} with ID {Id}", typeof(T).Name, entity.Id);
            return result.Entity;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error adding entity of type {EntityType} with ID {Id}", typeof(T).Name, entity.Id);
            throw;
        }
    }
    
    /// <summary>
    /// Adds multiple entities to the database in a batch
    /// </summary>
    /// <param name="entities">The entities to add</param>
    /// <returns>The number of entities added</returns>
    public async Task<int> AddRangeAsync(IEnumerable<T> entities)
    {
        try
        {
            var entityList = entities.ToList();
            _logger.LogDebug("Adding {Count} entities of type {EntityType}", entityList.Count, typeof(T).Name);
            
            await _context.Set<T>().AddRangeAsync(entityList);
            var result = await _context.SaveChangesAsync();
            
            _logger.LogDebug("Successfully added {Count} entities of type {EntityType}", result, typeof(T).Name);
            return result;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error adding entities of type {EntityType}", typeof(T).Name);
            throw;
        }
    }
    
    /// <summary>
    /// Gets an entity by its ID
    /// </summary>
    /// <param name="id">The entity ID</param>
    /// <returns>The entity if found, null otherwise</returns>
    public async Task<T?> GetByIdAsync(Guid id)
    {
        try
        {
            _logger.LogDebug("Retrieving entity of type {EntityType} with ID {Id}", typeof(T).Name, id);
            
            var result = await _context.Set<T>().FirstOrDefaultAsync(x => x.Id == id);
            
            if (result != null)
            {
                _logger.LogDebug("Found entity of type {EntityType} with ID {Id}", typeof(T).Name, id);
            }
            else
            {
                _logger.LogDebug("Entity of type {EntityType} with ID {Id} not found", typeof(T).Name, id);
            }
            
            return result;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error retrieving entity of type {EntityType} with ID {Id}", typeof(T).Name, id);
            throw;
        }
    }
    
    /// <summary>
    /// Updates an existing entity
    /// </summary>
    /// <param name="entity">The entity to update</param>
    /// <returns>The updated entity</returns>
    public async Task<T> UpdateAsync(T entity)
    {
        try
        {
            _logger.LogDebug("Updating entity of type {EntityType} with ID {Id}", typeof(T).Name, entity.Id);
            
            _context.Set<T>().Update(entity);
            await _context.SaveChangesAsync();
            
            _logger.LogDebug("Successfully updated entity of type {EntityType} with ID {Id}", typeof(T).Name, entity.Id);
            return entity;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error updating entity of type {EntityType} with ID {Id}", typeof(T).Name, entity.Id);
            throw;
        }
    }
    
    /// <summary>
    /// Deletes an entity by its ID
    /// </summary>
    /// <param name="id">The entity ID to delete</param>
    /// <returns>True if the entity was deleted, false if not found</returns>
    public async Task<bool> DeleteAsync(Guid id)
    {
        try
        {
            _logger.LogDebug("Deleting entity of type {EntityType} with ID {Id}", typeof(T).Name, id);
            
            var entity = await _context.Set<T>().FirstOrDefaultAsync(x => x.Id == id);
            if (entity == null)
            {
                _logger.LogDebug("Entity of type {EntityType} with ID {Id} not found for deletion", typeof(T).Name, id);
                return false;
            }
            
            _context.Set<T>().Remove(entity);
            await _context.SaveChangesAsync();
            
            _logger.LogDebug("Successfully deleted entity of type {EntityType} with ID {Id}", typeof(T).Name, id);
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error deleting entity of type {EntityType} with ID {Id}", typeof(T).Name, id);
            throw;
        }
    }
    
    /// <summary>
    /// Gets all entities
    /// </summary>
    /// <param name="skip">Number of items to skip (for pagination)</param>
    /// <param name="take">Number of items to take (for pagination)</param>
    /// <returns>Collection of entities</returns>
    public async Task<IEnumerable<T>> GetAllAsync(int? skip = null, int? take = null)
    {
        try
        {
            _logger.LogDebug("Retrieving entities of type {EntityType} (skip: {Skip}, take: {Take})", typeof(T).Name, skip, take);
            
            IQueryable<T> query = _context.Set<T>();
            
            if (skip.HasValue)
            {
                query = query.Skip(skip.Value);
            }
            
            if (take.HasValue)
            {
                query = query.Take(take.Value);
            }
            
            var result = await query.ToListAsync();
            
            _logger.LogDebug("Retrieved {Count} entities of type {EntityType}", result.Count, typeof(T).Name);
            return result;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error retrieving entities of type {EntityType}", typeof(T).Name);
            throw;
        }
    }
    
    /// <summary>
    /// Gets the total count of entities
    /// </summary>
    /// <returns>Total count of entities</returns>
    public async Task<int> CountAsync()
    {
        try
        {
            _logger.LogDebug("Counting entities of type {EntityType}", typeof(T).Name);
            
            var count = await _context.Set<T>().CountAsync();
            
            _logger.LogDebug("Found {Count} entities of type {EntityType}", count, typeof(T).Name);
            return count;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error counting entities of type {EntityType}", typeof(T).Name);
            throw;
        }
    }
}