namespace PacketProcessing.DTOs;

/// <summary>
/// Generic response result for API operations
/// </summary>
/// <typeparam name="T">The type of data being returned</typeparam>
public class ResponseResult<T>
{
    /// <summary>
    /// Indicates whether the operation was successful
    /// </summary>
    public bool Success { get; set; }
    
    /// <summary>
    /// The data payload (null if operation failed)
    /// </summary>
    public T? Data { get; set; }
    
    /// <summary>
    /// Error message (null if operation succeeded)
    /// </summary>
    public string? ErrorMessage { get; set; }
    
    /// <summary>
    /// HTTP status code
    /// </summary>
    public int StatusCode { get; set; }
    
    /// <summary>
    /// Timestamp of the response
    /// </summary>
    public DateTime Timestamp { get; set; } = DateTime.UtcNow;
    
    /// <summary>
    /// Creates a successful response
    /// </summary>
    /// <param name="data">The data to return</param>
    /// <param name="statusCode">HTTP status code (default: 200)</param>
    /// <returns>A successful ResponseResult</returns>
    public static ResponseResult<T> SuccessResult(T data, int statusCode = 200)
    {
        return new ResponseResult<T>
        {
            Success = true,
            Data = data,
            StatusCode = statusCode
        };
    }
    
    /// <summary>
    /// Creates a failed response
    /// </summary>
    /// <param name="errorMessage">Error message</param>
    /// <param name="statusCode">HTTP status code (default: 400)</param>
    /// <returns>A failed ResponseResult</returns>
    public static ResponseResult<T> ErrorResult(string errorMessage, int statusCode = 400)
    {
        return new ResponseResult<T>
        {
            Success = false,
            ErrorMessage = errorMessage,
            StatusCode = statusCode
        };
    }
    
    /// <summary>
    /// Creates a not found response
    /// </summary>
    /// <param name="errorMessage">Error message (default: "Resource not found")</param>
    /// <returns>A not found ResponseResult</returns>
    public static ResponseResult<T> NotFoundResult(string errorMessage = "Resource not found")
    {
        return ErrorResult(errorMessage, 404);
    }
    
    /// <summary>
    /// Creates a server error response
    /// </summary>
    /// <param name="errorMessage">Error message (default: "Internal server error")</param>
    /// <returns>A server error ResponseResult</returns>
    public static ResponseResult<T> ServerErrorResult(string errorMessage = "Internal server error")
    {
        return ErrorResult(errorMessage, 500);
    }
}

/// <summary>
/// Non-generic response result for operations that don't return data
/// </summary>
public class ResponseResult
{
    /// <summary>
    /// Indicates whether the operation was successful
    /// </summary>
    public bool Success { get; set; }
    
    /// <summary>
    /// Error message (null if operation succeeded)
    /// </summary>
    public string? ErrorMessage { get; set; }
    
    /// <summary>
    /// HTTP status code
    /// </summary>
    public int StatusCode { get; set; }
    
    /// <summary>
    /// Timestamp of the response
    /// </summary>
    public DateTime Timestamp { get; set; } = DateTime.UtcNow;
    
    /// <summary>
    /// Creates a successful response
    /// </summary>
    /// <param name="statusCode">HTTP status code (default: 200)</param>
    /// <returns>A successful ResponseResult</returns>
    public static ResponseResult SuccessResult(int statusCode = 200)
    {
        return new ResponseResult
        {
            Success = true,
            StatusCode = statusCode
        };
    }
    
    /// <summary>
    /// Creates a failed response
    /// </summary>
    /// <param name="errorMessage">Error message</param>
    /// <param name="statusCode">HTTP status code (default: 400)</param>
    /// <returns>A failed ResponseResult</returns>
    public static ResponseResult ErrorResult(string errorMessage, int statusCode = 400)
    {
        return new ResponseResult
        {
            Success = false,
            ErrorMessage = errorMessage,
            StatusCode = statusCode
        };
    }
    
    /// <summary>
    /// Creates a not found response
    /// </summary>
    /// <param name="errorMessage">Error message (default: "Resource not found")</param>
    /// <returns>A not found ResponseResult</returns>
    public static ResponseResult NotFoundResult(string errorMessage = "Resource not found")
    {
        return ErrorResult(errorMessage, 404);
    }
    
    /// <summary>
    /// Creates a server error response
    /// </summary>
    /// <param name="errorMessage">Error message (default: "Internal server error")</param>
    /// <returns>A server error ResponseResult</returns>
    public static ResponseResult ServerErrorResult(string errorMessage = "Internal server error")
    {
        return ErrorResult(errorMessage, 500);
    }
}
