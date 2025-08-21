using System.Net;
using System.Text.Json;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.Logging;

namespace PacketProcessing.Config;

/// <summary>
/// Global Exception Handler Middleware
/// 
/// Catches all unhandled exceptions and returns consistent error responses.
/// Maps exceptions to appropriate HTTP status codes and logs details.
/// </summary>
public class GlobalExceptionHandler
{
    private readonly RequestDelegate _next;
    private readonly ILogger<GlobalExceptionHandler> _logger;

    /// <summary>
    /// Initializes a new instance of the GlobalExceptionHandler
    /// </summary>
    /// <param name="next">The next middleware in the pipeline</param>
    public GlobalExceptionHandler(RequestDelegate next, ILogger<GlobalExceptionHandler> logger)
    {
        _next = next;
        _logger = logger;
    }

    /// <summary>
    /// Processes the HTTP request and handles any exceptions
    /// </summary>
    /// <param name="context">The HTTP context for the current request</param>
    /// <returns>A task representing the asynchronous operation</returns>
    public async Task InvokeAsync(HttpContext context)
    {
        try
        {
            await _next(context);
        }
        catch (Exception ex)
        {
            await HandleExceptionAsync(context, ex);
        }
    }

    /// <summary>
    /// Handles exceptions by creating appropriate HTTP responses
    /// </summary>
    /// <param name="context">The HTTP context for the current request</param>
    /// <param name="exception">The exception that was thrown</param>
    /// <returns>A task representing the asynchronous operation</returns>
    private async Task HandleExceptionAsync(HttpContext context, Exception exception)
    {
        var response = context.Response;
        response.ContentType = "application/json";

        // Check if it's an HTTP exception first
        if (exception is HttpRequestException httpException)
        {
            // Present HTTP exceptions as-is
            response.StatusCode = (int)httpException.StatusCode.GetValueOrDefault(HttpStatusCode.InternalServerError);
            
            var httpErrorResponse = new
            {
                StatusCode = httpException.StatusCode.GetValueOrDefault(HttpStatusCode.InternalServerError),
                Message = httpException.Message ?? "HTTP request failed",
                Timestamp = DateTime.UtcNow,
                RequestId = context.TraceIdentifier
            };

            // Log the HTTP exception
            _logger.LogError(httpException, "HTTP exception caught: {Message} with status {StatusCode} for request {RequestId} at {Path}",
                httpException.Message, httpException.StatusCode, context.TraceIdentifier, context.Request.Path);

            var httpResult = JsonSerializer.Serialize(httpErrorResponse, new JsonSerializerOptions
            {
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase
            });

            await response.WriteAsync(httpResult);
            return;
        }

        // For other exceptions, use the switch case
        var (statusCode, message) = exception switch
        {
            ArgumentNullException => (HttpStatusCode.BadRequest, exception.Message ?? "Required parameter is missing"),
            FileNotFoundException => (HttpStatusCode.NotFound, exception.Message ?? "File not found"),
            DirectoryNotFoundException => (HttpStatusCode.NotFound, exception.Message ?? "Directory not found"),
            UnauthorizedAccessException => (HttpStatusCode.Unauthorized, exception.Message ?? "Access denied"),
            InvalidOperationException => (HttpStatusCode.BadRequest, exception.Message ?? "Invalid operation"),
            KeyNotFoundException => (HttpStatusCode.NotFound, exception.Message ?? "Resource not found"),
            IOException => (HttpStatusCode.InternalServerError, exception.Message ?? "I/O error occurred"),
            NotSupportedException => (HttpStatusCode.BadRequest, exception.Message ?? "Operation not supported"),
            TimeoutException => (HttpStatusCode.RequestTimeout, exception.Message ?? "Operation timed out"),
            ArgumentException => (HttpStatusCode.BadRequest, exception.Message ?? "Invalid request parameters"),
            _ => (HttpStatusCode.InternalServerError, exception.Message ?? "An unexpected error occurred")
        };

        response.StatusCode = (int)statusCode;

        var errorResponse = new
        {
            StatusCode = statusCode,
            Message = message,
            Timestamp = DateTime.UtcNow,
            RequestId = context.TraceIdentifier
        };

        // Log the exception with context
        _logger.LogError(exception, "Global exception handler caught: {Message} for request {RequestId} at {Path}",
            exception.Message, context.TraceIdentifier, context.Request.Path);

        var result = JsonSerializer.Serialize(errorResponse, new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase
        });

        await response.WriteAsync(result);
    }
}

/// <summary>
/// Extension methods for GlobalExceptionHandler middleware
/// </summary>
public static class GlobalExceptionHandlerExtensions
{
    /// <summary>
    /// Adds the GlobalExceptionHandler middleware to the application pipeline
    /// </summary>
    /// <param name="builder">The application builder instance</param>
    /// <returns>The application builder for method chaining</returns>
    public static IApplicationBuilder UseGlobalExceptionHandler(this IApplicationBuilder builder)
    {
        return builder.UseMiddleware<GlobalExceptionHandler>();
    }
}