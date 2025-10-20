using System.Buffers;
using System.Collections.Concurrent;
using System.Net;
using System.Text;
using System.Xml.Linq;
using PacketProcessing.Utils.Exceptions;

namespace PacketProcessing.Utils.Parsers
{
    /// <summary>
    /// Reassembles HTTP/XML (SOAP) carried over TCP from raw Ethernet frames.
    /// - Accepts segments out-of-order.
    /// - Supports HTTP/1.1 keep-alive (multiple messages per flow).
    /// - Returns an XDocument when the next full HTTP body is available.
    /// - Otherwise throws ParserStreamNotCompletedException.
    /// </summary>
    public static class HttpXmlReassembler
    {
        // ---------- Per-direction TCP flow state ----------
        private sealed class FlowState
        {
            // Contiguous application bytes
            public byte[] Buf = [];
            public int Len = 0;

            // TCP reassembly
            public uint? NextSeq; // next expected seq
            public readonly SortedDictionary<uint, byte[]> OOO = new(); // out-of-order segs
            public DateTime Last = DateTime.UtcNow;

            // HTTP framing for current message
            public int HeaderEnd = -1;     // index of \r\n\r\n
            public int ContentLength = -1; // if present
            public bool Chunked = false;

            public readonly object Gate = new();
        }

        private readonly struct Key : IEquatable<Key>
        {
            public readonly IPAddress Src; public readonly ushort SP;
            public readonly IPAddress Dst; public readonly ushort DP;
            public Key(IPAddress s, ushort sp, IPAddress d, ushort dp) { Src = s; SP = sp; Dst = d; DP = dp; }
            public bool Equals(Key o) => Src.Equals(o.Src) && Dst.Equals(o.Dst) && SP == o.SP && DP == o.DP;
            public override bool Equals(object? obj) => obj is Key k && Equals(k);
            public override int GetHashCode() => HashCode.Combine(Src, SP, Dst, DP);
        }

        private static readonly ConcurrentDictionary<Key, FlowState> Flows = new();

        // ---------------- PUBLIC API ----------------
        /// <summary>
        /// Feed one Ethernet frame (IPv4/TCP carrying HTTP/XML). If the next full HTTP body
        /// on this flow is complete, returns it parsed as XDocument. Otherwise throws ParserStreamNotCompletedException.
        /// </summary>
        public static XDocument AssembleXmlOrThrow(ReadOnlySpan<byte> frame)
        {
            // Parse L2/L3/L4 and get TCP payload + 4-tuple + seq
            if (!TryParseEtherIpv4Tcp(frame, out var k, out uint seq, out var payload))
                throw new ParserStreamNotCompletedException("Not IPv4/TCP or invalid frame.");

            var st = Flows.GetOrAdd(k, _ => new FlowState());
            lock (st.Gate)
            {
                st.Last = DateTime.UtcNow;

                // ----- TCP reassembly (out-of-order tolerant) -----
                AddSegment(st, seq, payload);

                // ----- HTTP header detection -----
                if (st.HeaderEnd < 0)
                {
                    st.HeaderEnd = FindHeaderEnd(st.Buf.AsSpan(0, st.Len));
                    if (st.HeaderEnd < 0)
                        throw new ParserStreamNotCompletedException("HTTP headers incomplete.");

                    (st.ContentLength, st.Chunked) = ParseHeaders(st.Buf.AsSpan(0, st.HeaderEnd));
                }

                // ----- Body framing -----
                ReadOnlySpan<byte> bodySpan;
                int consumedBytes;

                if (st.Chunked)
                {
                    var bodyView = st.Buf.AsSpan(st.HeaderEnd + 4, st.Len - (st.HeaderEnd + 4));
                    if (!TryReadChunked(bodyView, out int bodyLen, out int totalConsumed))
                        throw new ParserStreamNotCompletedException("Chunked body incomplete.");
                    bodySpan = bodyView.Slice(0, bodyLen);
                    consumedBytes = st.HeaderEnd + 4 + totalConsumed;
                }
                else
                {
                    if (st.ContentLength < 0)
                        throw new ParserStreamNotCompletedException("Unknown body length.");
                    int have = st.Len - (st.HeaderEnd + 4);
                    if (have < st.ContentLength)
                        throw new ParserStreamNotCompletedException($"Body incomplete {have}/{st.ContentLength}.");
                    bodySpan = st.Buf.AsSpan(st.HeaderEnd + 4, st.ContentLength);
                    consumedBytes = st.HeaderEnd + 4 + st.ContentLength;
                }

                // ----- Parse XML (prefix-agnostic) -----
                // Make a tight copy for safe XML parse
                var tight = bodySpan.ToArray();
                using var ms = new MemoryStream(tight, writable: false);
                var xdoc = XDocument.Load(ms, LoadOptions.PreserveWhitespace | LoadOptions.SetLineInfo);

                // ----- Consume used bytes and reset HTTP state for next message -----
                ConsumePrefix(st, consumedBytes);
                ResetHttp(st);

                return xdoc;
            }
        }

        // ---------------- TCP reassembly core ----------------
        private static void AddSegment(FlowState st, uint seq, ReadOnlySpan<byte> data)
        {
            if (data.Length == 0) return;

            if (st.NextSeq == null)
            {
                // First data observed
                EnsureCap(st, st.Len + data.Length);
                data.CopyTo(st.Buf.AsSpan(st.Len));
                st.Len += data.Length;
                st.NextSeq = seq + (uint)data.Length;
                // Try to merge any queued OOO segments that now attach
                MergeOOO(st);
                return;
            }

            uint exp = st.NextSeq.Value;
            if (seq == exp)
            {
                // contiguous
                EnsureCap(st, st.Len + data.Length);
                data.CopyTo(st.Buf.AsSpan(st.Len));
                st.Len += data.Length;
                st.NextSeq = exp + (uint)data.Length;
                MergeOOO(st);
            }
            else if ((int)(seq - exp) < 0)
            {
                // retransmit/overlap: append only the new tail beyond exp
                int overlap = (int)(exp - seq);
                if (overlap < data.Length)
                {
                    var tail = data.Slice(overlap);
                    EnsureCap(st, st.Len + tail.Length);
                    tail.CopyTo(st.Buf.AsSpan(st.Len));
                    st.Len += tail.Length;
                    st.NextSeq = exp + (uint)tail.Length;
                    MergeOOO(st);
                }
            }
            else
            {
                // future segment → stash
                var rent = ArrayPool<byte>.Shared.Rent(data.Length);
                data.CopyTo(rent.AsSpan(0, data.Length));
                st.OOO[seq] = rent.AsMemory(0, data.Length).ToArray();
                ArrayPool<byte>.Shared.Return(rent);
            }
        }

        private static void MergeOOO(FlowState st)
        {
            while (st.OOO.Count > 0)
            {
                using var it = st.OOO.GetEnumerator();
                if (!it.MoveNext()) break;
                var (k, seg) = (it.Current.Key, it.Current.Value);
                if (st.NextSeq == null || k != st.NextSeq.Value) break;

                EnsureCap(st, st.Len + seg.Length);
                seg.AsSpan().CopyTo(st.Buf.AsSpan(st.Len));
                st.Len += seg.Length;
                st.NextSeq = st.NextSeq.Value + (uint)seg.Length;
                st.OOO.Remove(k);
                ArrayPool<byte>.Shared.Return(seg);
            }
        }

        // ---------------- HTTP helpers ----------------
        private static int FindHeaderEnd(ReadOnlySpan<byte> d)
        {
            for (int i = 0; i + 3 < d.Length; i++)
                if (d[i] == 13 && d[i + 1] == 10 && d[i + 2] == 13 && d[i + 3] == 10)
                    return i;
            return -1;
        }

        private static (int contentLength, bool chunked) ParseHeaders(ReadOnlySpan<byte> headers)
        {
            var h = Encoding.ASCII.GetString(headers); // small
            int len = -1;
            bool chunked = h.IndexOf("\nTransfer-Encoding:", StringComparison.OrdinalIgnoreCase) >= 0
                           && h.IndexOf("chunked", StringComparison.OrdinalIgnoreCase) >= 0;

            var cl = h.IndexOf("\nContent-Length:", StringComparison.OrdinalIgnoreCase);
            if (cl >= 0)
            {
                var rest = h[(cl + 16)..];
                int nl = rest.IndexOf('\n');
                var num = (nl >= 0 ? rest[..nl] : rest).Trim();
                if (int.TryParse(num, out var n)) len = n;
            }
            return (len, chunked);
        }

        private static bool TryReadChunked(ReadOnlySpan<byte> bodyStart, out int bodyLen, out int totalConsumed)
        {
            bodyLen = 0; totalConsumed = 0;
            while (true)
            {
                int crlf = IndexOfCrlf(bodyStart.Slice(totalConsumed));
                if (crlf < 0) return false;

                var sizeHex = bodyStart.Slice(totalConsumed, crlf);
                if (!int.TryParse(Encoding.ASCII.GetString(sizeHex),
                    System.Globalization.NumberStyles.HexNumber, null, out int sz))
                    return false;

                totalConsumed += crlf + 2; // skip size line

                if (bodyStart.Length < totalConsumed + sz + 2) return false; // need chunk + CRLF
                totalConsumed += sz;

                if (!(bodyStart[totalConsumed] == 13 && bodyStart[totalConsumed + 1] == 10))
                    return false;
                totalConsumed += 2;

                bodyLen += sz;
                if (sz == 0) break; // terminating chunk
            }
            return true;
        }

        private static int IndexOfCrlf(ReadOnlySpan<byte> s)
        {
            for (int i = 0; i + 1 < s.Length; i++)
                if (s[i] == 13 && s[i + 1] == 10) return i;
            return -1;
        }

        // ---------------- Buffer utilities ----------------
        private static void EnsureCap(FlowState st, int need)
        {
            if (st.Buf.Length >= need) return;
            int newCap = Math.Max(need, st.Buf.Length == 0 ? 16 * 1024 : st.Buf.Length * 2);
            var n = ArrayPool<byte>.Shared.Rent(newCap);
            if (st.Len > 0) st.Buf.AsSpan(0, st.Len).CopyTo(n);
            ArrayPool<byte>.Shared.Return(st.Buf);
            st.Buf = n;
        }

        private static void ConsumePrefix(FlowState st, int count)
        {
            if (count <= 0) return;
            if (count >= st.Len) { st.Len = 0; return; }
            st.Buf.AsSpan(count, st.Len - count).CopyTo(st.Buf.AsSpan(0));
            st.Len -= count;
        }

        private static void ResetHttp(FlowState st)
        {
            st.HeaderEnd = -1;
            st.ContentLength = -1;
            st.Chunked = false;
        }

        // ---------------- L2/L3/L4 parser ----------------
        private static bool TryParseEtherIpv4Tcp(
            ReadOnlySpan<byte> frame,
            out Key key, out uint seq, out ReadOnlySpan<byte> tcpPayload)
        {
            key = default; seq = 0; tcpPayload = default;

            if (frame.Length < 14) return false;
            ushort etherType = (ushort)((frame[12] << 8) | frame[13]);
            int ipOffset = 14;

            // VLAN tagged
            if (etherType == 0x8100)
            {
                if (frame.Length < 18) return false;
                etherType = (ushort)((frame[16] << 8) | frame[17]);
                ipOffset = 18;
            }

            if (etherType != 0x0800 || frame.Length < ipOffset + 20) return false; // IPv4
            var ip = frame[ipOffset..];
            int ihl = (ip[0] & 0x0F) * 4;
            if (ihl < 20 || frame.Length < ipOffset + ihl) return false;
            if (ip[9] != 6) return false; // TCP

            var src = new IPAddress(ip.Slice(12, 4));
            var dst = new IPAddress(ip.Slice(16, 4));

            int tcpOffset = ipOffset + ihl;
            if (frame.Length < tcpOffset + 20) return false;

            var tcp = frame.Slice(tcpOffset);
            ushort sp = (ushort)((tcp[0] << 8) | tcp[1]);
            ushort dp = (ushort)((tcp[2] << 8) | tcp[3]);
            seq = (uint)((tcp[4] << 24) | (tcp[5] << 16) | (tcp[6] << 8) | tcp[7]);
            int doff = (tcp[12] >> 4) * 4;
            if (doff < 20 || frame.Length < tcpOffset + doff) return false;

            tcpPayload = frame.Slice(tcpOffset + doff);
            key = new Key(src, sp, dst, dp);
            return true;
        }
    }
}