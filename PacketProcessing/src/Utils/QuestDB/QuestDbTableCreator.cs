using Microsoft.Extensions.Logging;
using Npgsql;
using PacketProcessing.Entities;
using PacketProcessing.Entities.Packet;

namespace PacketProcessing.Utils.QuestDB;

/// <summary>
/// Service for creating and managing QuestDB tables for packet entities
/// </summary>
public class QuestDbTableCreator
{
    private readonly ILogger<QuestDbTableCreator> _logger;
    private readonly string _connectionString;

    public QuestDbTableCreator(ILogger<QuestDbTableCreator> logger, string connectionString)
    {
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _connectionString = connectionString ?? throw new ArgumentNullException(nameof(connectionString));
    }

    /// <summary>
    /// Ensures all packet entity tables exist in QuestDB
    /// </summary>
    /// <returns>True if any tables were created, false if all already existed</returns>
    public async Task<bool> EnsureTablesExistAsync()
    {
        try
        {
            _logger.LogInformation("Checking if QuestDB packet tables exist...");
            
            var tablesCreated = false;
            
            // Create tables for each packet entity type
            if (await CreateMotionPacketsTableAsync())
                tablesCreated = true;
                
            if (await CreateOnVifPacketsTableAsync())
                tablesCreated = true;
                
            if (await CreateSafetyPacketsTableAsync())
                tablesCreated = true;

            if (tablesCreated)
            {
                _logger.LogInformation("QuestDB packet tables created successfully");
            }
            else
            {
                _logger.LogInformation("All QuestDB packet tables already exist");
            }
            
            return tablesCreated;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "An error occurred while ensuring QuestDB packet tables exist");
            throw;
        }
    }

    /// <summary>
    /// Creates the motion_packets table if it doesn't exist
    /// </summary>
    /// <returns>True if table was created, false if it already existed</returns>
    private async Task<bool> CreateMotionPacketsTableAsync()
    {
        const string tableName = "motion_packets";
        
        if (await TableExistsAsync(tableName))
        {
            _logger.LogDebug("Table {TableName} already exists in QuestDB", tableName);
            return false;
        }

        var createTableSql = $@"
            CREATE TABLE {tableName} (
                timestamp TIMESTAMP,
                id SYMBOL,
                type BOOLEAN,
                opCode SYMBOL,
                opCodeDescription SYMBOL,
                axis INT,
                floatValue FLOAT
            ) TIMESTAMP(timestamp) PARTITION BY DAY;";

        await ExecuteSqlAsync(createTableSql);
        _logger.LogInformation("Table {TableName} created successfully in QuestDB", tableName);
        return true;
    }

    /// <summary>
    /// Creates the onvif_packets table if it doesn't exist
    /// </summary>
    /// <returns>True if table was created, false if it already existed</returns>
    private async Task<bool> CreateOnVifPacketsTableAsync()
    {
        const string tableName = "onvif_packets";
        
        if (await TableExistsAsync(tableName))
        {
            _logger.LogDebug("Table {TableName} already exists in QuestDB", tableName);
            return false;
        }

        var createTableSql = $@"
            CREATE TABLE {tableName} (
                timestamp TIMESTAMP,
                id SYMBOL,
                type BOOLEAN,
                description SYMBOL,
                zoom FLOAT,
                measurement FLOAT
            ) TIMESTAMP(timestamp) PARTITION BY DAY;";

        await ExecuteSqlAsync(createTableSql);
        _logger.LogInformation("Table {TableName} created successfully in QuestDB", tableName);
        return true;
    }

    /// <summary>
    /// Creates the safety_packets table if it doesn't exist
    /// </summary>
    /// <returns>True if table was created, false if it already existed</returns>
    private async Task<bool> CreateSafetyPacketsTableAsync()
    {
        const string tableName = "safety_packets";
        
        if (await TableExistsAsync(tableName))
        {
            _logger.LogDebug("Table {TableName} already exists in QuestDB", tableName);
            return false;
        }

        var createTableSql = $@"
            CREATE TABLE {tableName} (
                timestamp TIMESTAMP,
                id SYMBOL,
                type BOOLEAN,
                opCode SYMBOL,
                opCodeDescription SYMBOL,
                state SYMBOL
            ) TIMESTAMP(timestamp) PARTITION BY DAY;";

        await ExecuteSqlAsync(createTableSql);
        _logger.LogInformation("Table {TableName} created successfully in QuestDB", tableName);
        return true;
    }

    /// <summary>
    /// Checks if a table exists in QuestDB
    /// </summary>
    /// <param name="tableName">The name of the table to check</param>
    /// <returns>True if the table exists, false otherwise</returns>
    private async Task<bool> TableExistsAsync(string tableName)
    {
        var sql = $@"
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_name = '{tableName}'";

        using var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync();
        
        using var command = new NpgsqlCommand(sql, connection);
        var count = await command.ExecuteScalarAsync();
        
        return Convert.ToInt32(count) > 0;
    }

    /// <summary>
    /// Executes SQL command against QuestDB
    /// </summary>
    /// <param name="sql">The SQL command to execute</param>
    private async Task ExecuteSqlAsync(string sql)
    {
        using var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync();
        
        using var command = new NpgsqlCommand(sql, connection);
        await command.ExecuteNonQueryAsync();
    }

    /// <summary>
    /// Gets the table name for a packet entity type
    /// </summary>
    /// <typeparam name="T">The packet entity type</typeparam>
    /// <returns>The table name</returns>
    public static string GetTableName<T>() where T : BasePacketEntity
    {
        var tempEntity = Activator.CreateInstance<T>();
        return tempEntity.TableName;
    }
    
    /// <summary>
    /// Gets the QuestDB connection string
    /// </summary>
    /// <returns>The connection string</returns>
    public string GetConnectionString()
    {
        return _connectionString;
    }
}
