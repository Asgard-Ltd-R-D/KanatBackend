using Microsoft.Extensions.Logging;
using System.Text;

namespace PacketProcessing.Utils.QuestDB;

/// <summary>
/// Client for interacting with QuestDB via HTTP API
/// Similar to AppDbContext for Entity Framework, but for QuestDB operations
/// </summary>
public class QuestClient : IDisposable
{
    private readonly HttpClient _httpClient;
    private readonly string _baseUrl;
    private readonly ILogger _logger;
    private bool _disposed;

    public QuestClient(string connectionString, ILogger logger)
    {
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        
        // Initialize HTTP client
        _httpClient = new HttpClient();
        _httpClient.Timeout = TimeSpan.FromSeconds(10);
        
        // Extract connection details
        var host = ExtractHostFromConnectionString(connectionString);
        var port = "9000"; // QuestDB HTTP API port
        _baseUrl = $"http://{host}:{port}";
        
        _logger.LogDebug("Initialized QuestClient with base URL: {BaseUrl}", _baseUrl);
    }

    /// <summary>
    /// Executes a query against QuestDB and returns the raw response
    /// </summary>
    /// <param name="query">The SQL query to execute</param>
    /// <returns>The raw response from QuestDB</returns>
    public async Task<string> ExecuteQueryAsync(string query)
    {
        if (string.IsNullOrWhiteSpace(query))
            throw new ArgumentException("Query cannot be null or empty", nameof(query));

        var url = $"{_baseUrl}/exec?query={Uri.EscapeDataString(query)}";
        
        _logger.LogDebug("Executing QuestDB query: {Query} at {Url}", query, url);
        
        try
        {
            var response = await _httpClient.GetAsync(url);
            response.EnsureSuccessStatusCode();
            
            var result = await response.Content.ReadAsStringAsync();
            _logger.LogDebug("QuestDB query executed successfully, response length: {Length}", result.Length);
            
            return result;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to execute QuestDB query: {Query}", query);
            throw;
        }
    }

    /// <summary>
    /// Executes a query that doesn't return data (like TRUNCATE, INSERT, etc.)
    /// </summary>
    /// <param name="query">The SQL query to execute</param>
    public async Task ExecuteNonQueryAsync(string query)
    {
        if (string.IsNullOrWhiteSpace(query))
            throw new ArgumentException("Query cannot be null or empty", nameof(query));

        var url = $"{_baseUrl}/exec?query={Uri.EscapeDataString(query)}";
        
        _logger.LogDebug("Executing QuestDB non-query: {Query} at {Url}", query, url);
        
        try
        {
            var response = await _httpClient.GetAsync(url);
            response.EnsureSuccessStatusCode();
            
            _logger.LogDebug("QuestDB non-query executed successfully");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to execute QuestDB non-query: {Query}", query);
            throw;
        }
    }

    /// <summary>
    /// Executes a query and returns the result as a collection of entities
    /// </summary>
    /// <typeparam name="T">The type of entity to return</typeparam>
    /// <param name="query">The SQL query to execute</param>
    /// <param name="parser">Function to parse the raw response into entities</param>
    /// <returns>Collection of entities</returns>
    public async Task<IEnumerable<T>> ExecuteQueryAsync<T>(string query, Func<string, IEnumerable<T>> parser)
    {
        if (string.IsNullOrWhiteSpace(query))
            throw new ArgumentException("Query cannot be null or empty", nameof(query));
        
        if (parser == null)
            throw new ArgumentNullException(nameof(parser));

        var rawResponse = await ExecuteQueryAsync(query);
        return parser(rawResponse);
    }

    /// <summary>
    /// Checks if QuestDB is accessible
    /// </summary>
    /// <returns>True if QuestDB is accessible, false otherwise</returns>
    public async Task<bool> IsAccessibleAsync()
    {
        try
        {
            var response = await _httpClient.GetAsync($"{_baseUrl}/health");
            return response.IsSuccessStatusCode;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "QuestDB is not accessible at {BaseUrl}", _baseUrl);
            return false;
        }
    }

    /// <summary>
    /// Gets the base URL for QuestDB operations
    /// </summary>
    public string BaseUrl => _baseUrl;

    /// <summary>
    /// Extracts host from QuestDB connection string
    /// </summary>
    private static string ExtractHostFromConnectionString(string connectionString)
    {
        if (string.IsNullOrWhiteSpace(connectionString))
            return "localhost";

        var parts = connectionString.Split(';');
        var hostPart = parts.FirstOrDefault(p => p.StartsWith("Host="));
        return hostPart?.Substring(5) ?? "localhost";
    }

    public void Dispose()
    {
        Dispose(true);
        GC.SuppressFinalize(this);
    }

    protected virtual void Dispose(bool disposing)
    {
        if (!_disposed && disposing)
        {
            _httpClient?.Dispose();
            _disposed = true;
        }
    }
}
