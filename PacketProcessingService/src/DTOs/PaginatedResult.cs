namespace PacketProcessing.DTOs;

/// <summary>
/// Generic paginated result for API operations that return paginated data
/// </summary>
/// <typeparam name="T">The type of data being returned</typeparam>
public class PaginatedResult<T>
{
    /// <summary>
    /// The collection of items for the current page
    /// </summary>
    public IEnumerable<T> Items { get; set; } = new List<T>();
    
    /// <summary>
    /// Current page number (1-based)
    /// </summary>
    public int Page { get; set; }
    
    /// <summary>
    /// Number of items per page
    /// </summary>
    public int PageSize { get; set; }
    
    /// <summary>
    /// Total number of items across all pages
    /// </summary>
    public int TotalCount { get; set; }
    
    /// <summary>
    /// Total number of pages
    /// </summary>
    public int TotalPages { get; set; }
    
    /// <summary>
    /// Indicates if there is a previous page
    /// </summary>
    public bool HasPreviousPage { get; set; }
    
    /// <summary>
    /// Indicates if there is a next page
    /// </summary>
    public bool HasNextPage { get; set; }
    
    /// <summary>
    /// Timestamp of the response
    /// </summary>
    public DateTime Timestamp { get; set; } = DateTime.UtcNow;
    
    /// <summary>
    /// Creates a paginated result from a collection and pagination parameters
    /// </summary>
    /// <param name="items">The items for the current page</param>
    /// <param name="page">Current page number</param>
    /// <param name="pageSize">Number of items per page</param>
    /// <param name="totalCount">Total number of items</param>
    /// <returns>A PaginatedResult</returns>
    public static PaginatedResult<T> Create(IEnumerable<T> items, int page, int pageSize, int totalCount)
    {
        var totalPages = (int)Math.Ceiling((double)totalCount / pageSize);
        
        return new PaginatedResult<T>
        {
            Items = items,
            Page = page,
            PageSize = pageSize,
            TotalCount = totalCount,
            TotalPages = totalPages,
            HasPreviousPage = page > 1,
            HasNextPage = page < totalPages
        };
    }
    
    /// <summary>
    /// Creates an empty paginated result
    /// </summary>
    /// <param name="page">Current page number (default: 1)</param>
    /// <param name="pageSize">Number of items per page (default: 10)</param>
    /// <returns>An empty PaginatedResult</returns>
    public static PaginatedResult<T> Empty(int page = 1, int pageSize = 10)
    {
        return new PaginatedResult<T>
        {
            Items = new List<T>(),
            Page = page,
            PageSize = pageSize,
            TotalCount = 0,
            TotalPages = 0,
            HasPreviousPage = false,
            HasNextPage = false
        };
    }
    
    /// <summary>
    /// Creates a paginated result from a full collection with automatic pagination
    /// </summary>
    /// <param name="allItems">All items to paginate</param>
    /// <param name="page">Current page number (1-based)</param>
    /// <param name="pageSize">Number of items per page</param>
    /// <returns>A PaginatedResult with the specified page of items</returns>
    public static PaginatedResult<T> FromCollection(IEnumerable<T> allItems, int page, int pageSize)
    {
        var itemsList = allItems.ToList();
        var totalCount = itemsList.Count;
        var skip = (page - 1) * pageSize;
        var pageItems = itemsList.Skip(skip).Take(pageSize);
        
        return Create(pageItems, page, pageSize, totalCount);
    }
}

/// <summary>
/// Pagination parameters for API requests
/// </summary>
public class PaginationParameters
{
    /// <summary>
    /// Page number (1-based, default: 1)
    /// </summary>
    public int Page { get; set; } = 1;
    
    /// <summary>
    /// Number of items per page (default: 10, max: 1000)
    /// </summary>
    public int PageSize { get; set; } = 10;
    
    /// <summary>
    /// Validates and normalizes pagination parameters
    /// </summary>
    /// <returns>Normalized pagination parameters</returns>
    public PaginationParameters Normalize()
    {
        return new PaginationParameters
        {
            Page = Math.Max(1, Page),
            PageSize = Math.Clamp(PageSize, 1, 1000)
        };
    }
    
    /// <summary>
    /// Calculates the number of items to skip for the current page
    /// </summary>
    /// <returns>Number of items to skip</returns>
    public int GetSkip()
    {
        var normalized = Normalize();
        return (normalized.Page - 1) * normalized.PageSize;
    }
    
    /// <summary>
    /// Calculates the number of items to take for the current page
    /// </summary>
    /// <returns>Number of items to take</returns>
    public int GetTake()
    {
        return Normalize().PageSize;
    }
}
