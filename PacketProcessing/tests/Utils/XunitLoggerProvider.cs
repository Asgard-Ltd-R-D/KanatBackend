// TestLogging/XunitLogger.cs
using System;
using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;
using Xunit.Abstractions;

public sealed class XunitLoggerProvider : ILoggerProvider
{
    private readonly ITestOutputHelper _output;
    private readonly ConcurrentDictionary<string, XunitLogger> _loggers = new();
    private readonly Func<string, LogLevel, bool>? _filter;

    public XunitLoggerProvider(ITestOutputHelper output, Func<string, LogLevel, bool>? filter = null)
    {
        _output = output;
        _filter = filter;
    }

    public ILogger CreateLogger(string categoryName) =>
        _loggers.GetOrAdd(categoryName, name => new XunitLogger(name, _output, _filter));

    public void Dispose() { }

    private sealed class XunitLogger : ILogger
    {
        private readonly string _name;
        private readonly ITestOutputHelper _output;
        private readonly Func<string, LogLevel, bool>? _filter;

        public XunitLogger(string name, ITestOutputHelper output, Func<string, LogLevel, bool>? filter)
        {
            _name = name;
            _output = output;
            _filter = filter;
        }

        public IDisposable BeginScope<TState>(TState state) => NullScope.Instance;

        public bool IsEnabled(LogLevel logLevel) =>
            _filter?.Invoke(_name, logLevel) ?? true;

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state,
                                Exception? exception, Func<TState, Exception?, string> formatter)
        {
            if (!IsEnabled(logLevel)) return;
            var msg = formatter(state, exception);
            _output.WriteLine($"[{DateTime.UtcNow:O}] {logLevel,-11} {_name}: {msg}");
            if (exception != null)
                _output.WriteLine(exception.ToString());
        }

        private sealed class NullScope : IDisposable { public static readonly NullScope Instance = new(); public void Dispose() { } }
    }
}
