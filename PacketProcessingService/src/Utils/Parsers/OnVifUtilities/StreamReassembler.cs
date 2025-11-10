using System.Collections.Concurrent;
using System.Text;
using System.Text.RegularExpressions;

namespace PacketProcessing.Utils.Parsers.OnVifUtilities;

public record TcpKey(string SrcIP, int SrcPort, string DstIP, int DstPort);

public class StreamReassembler
{
    private readonly ConcurrentDictionary<TcpKey, SessionBuffer> _sessions = new();
    private readonly TimeSpan _timeout = TimeSpan.FromSeconds(5); // The timeout for the packets to stay on memory

    public void AddSegment(string srcIP, int srcPort, string dstIP, int dstPort, int seq, byte[] data)
    {
        if (data.Length == 0) return;

        var key = new TcpKey(srcIP, srcPort, dstIP, dstPort);
        var session = _sessions.GetOrAdd(key, _ => new SessionBuffer(_timeout));
        session.AddSegment(seq, data);
    }

    public string? TryReassembleXml(string srcIP, int srcPort, string dstIP, int dstPort)
    {
        var key = new TcpKey(srcIP, srcPort, dstIP, dstPort);
        if (!_sessions.TryGetValue(key, out var session)) return null;

        var combined = session.GetOrderedPayload();

        // Convert bytes to ASCII or UTF8 depending on protocol
        string text = Encoding.UTF8.GetString(combined);

        // Try to find SOAP envelope
        string? xml = ExtractEnvelope(text);
        return xml;
    }

    private static string? ExtractEnvelope(string text)
    {
        // Two possible tag pairs
        var soapPattern = @"<SOAP-ENV:Envelope[\s\S]*?</SOAP-ENV:Envelope>";
        var sPattern = @"<s:Envelope[\s\S]*?</s:Envelope>";

        var match = Regex.Match(text, soapPattern);

        // The SOAP pattern is not found, try the S pattern
        if (!match.Success)
            match = Regex.Match(text, sPattern);

        return match.Success ? match.Value : null;
    }

      private class SessionBuffer
    {
        private readonly ConcurrentDictionary<int, byte[]> _segments = new();
        private readonly TimeSpan _timeout;
        private CancellationTokenSource _cts = new();
        private readonly object _lock = new();

        public SessionBuffer(TimeSpan timeout)
        {
            _timeout = timeout;
            StartTimeoutWatcher();
        }

        public void AddSegment(int seq, byte[] data)
        {
            _segments[seq] = data;
            ResetTimer(); // reset timeout when new data arrives
        }

        public byte[] GetOrderedPayload()
        {
            return _segments
                .OrderBy(kv => kv.Key)
                .SelectMany(kv => kv.Value)
                .ToArray();
        }

        private void StartTimeoutWatcher()
        {
            _ = Task.Run(async () =>
            {
                while (true)
                {
                    try
                    {
                        await Task.Delay(_timeout, _cts.Token);
                        // Timeout reached — clear stale data
                        _segments.Clear();
                    }
                    catch (TaskCanceledException)
                    {
                        // Timer was reset, continue waiting
                        continue;
                    }
                }
            });
        }

        private void ResetTimer()
        {
            lock (_lock)
            {
                _cts.Cancel();
                _cts.Dispose();
                _cts = new CancellationTokenSource();
            }
        }
    }
}
