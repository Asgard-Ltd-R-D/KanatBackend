using System;

namespace PacketProcessing.Utils.Exceptions;

/// <summary>
/// Exception thrown when a parser encounters an incomplete TCP stream that needs more segments.
/// This is not a true error - it indicates the stream is still being assembled.
/// </summary>
public class ParserStreamNotCompletedException : Exception
{
    public ParserStreamNotCompletedException() : base()
    {
    }

    public ParserStreamNotCompletedException(string message) : base(message)
    {
    }

    public ParserStreamNotCompletedException(string message, Exception innerException) : base(message, innerException)
    {
    }
}

