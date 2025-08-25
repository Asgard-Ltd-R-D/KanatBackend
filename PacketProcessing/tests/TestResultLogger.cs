using Microsoft.Extensions.Logging;

namespace PacketProcessing.Tests;

/// <summary>
/// Provides clear and concise test result logging
/// </summary>
public static class TestResultLogger
{
    private static readonly ILogger Logger = LoggerFactory.Create(builder => builder.AddConsole())
        .CreateLogger("TestResults");

    /// <summary>
    /// Logs a test result with clear pass/fail status and key information
    /// </summary>
    public static void LogTestResult(string testName, bool passed, string? input = null, string? expected = null, string? actual = null, string? reason = null)
    {
        var status = passed ? "✅ PASS" : "❌ FAIL";
        var result = $"{status} | {testName}";
        
        if (!passed && !string.IsNullOrEmpty(reason))
        {
            result += $" | Reason: {reason}";
        }
        
        if (!string.IsNullOrEmpty(input))
        {
            result += $" | Input: {input}";
        }
        
        if (!string.IsNullOrEmpty(expected))
        {
            result += $" | Expected: {expected}";
        }
        
        if (!string.IsNullOrEmpty(actual))
        {
            result += $" | Actual: {actual}";
        }
        
        Logger.LogInformation(result);
    }

    /// <summary>
    /// Logs a simple test result with just the test name and status
    /// </summary>
    public static void LogSimpleResult(string testName, bool passed)
    {
        LogTestResult(testName, passed);
    }
}
