using System.Buffers;
using System.Collections.Concurrent;
using System.Net;
using PacketProcessing.Utils.Exceptions;

namespace PacketProcessing.Utils.Parsers.OnvifUtilities;

public static class OnVifPacketParserUtilities
{
    // Minimal per-direction flow buffer (src:port > dst:port)
    private sealed class S {
         public byte[] B = []; 
         public int L; 
         public int H=-1; 
         public int CL=-1; 
         public readonly object K=new(); 
    }

    private static readonly ConcurrentDictionary<string, S> F = new();

    private static string K(IPAddress a, ushort ap, IPAddress b, ushort bp) => $"{a}:{ap}>{b}:{bp}";

    /// <summary>
    /// Assemble COMPLETE HTTP body (SOAP XML) across TCP segments for one flow message.
    /// Returns the body bytes. If not complete yet – throws ParserStreamNotCompletedException.
    /// </summary>
    public static ReadOnlyMemory<byte> AssembleCompleteHttpBody(ReadOnlySpan<byte> raw)
    {
        // --- local helpers (kept tiny) ---
        static bool TryParse(ReadOnlySpan<byte> f,
                                out IPAddress s, out ushort sp, out IPAddress d, out ushort dp,
                                out ReadOnlySpan<byte> pay)
        {
            s=d=IPAddress.None; sp=dp=0; pay=default;

            if (f.Length < 14) return false;

            ushort et = (ushort)((f[12]<<8)|f[13]); int ipOff=14;

            if (et==0x8100){ if (f.Length<18) return false; et=(ushort)((f[16]<<8)|f[17]); ipOff=18; }
            if (et!=0x0800 || f.Length<ipOff+20) return false; // IPv4

            var ip=f.Slice(ipOff); int ihl=(ip[0]&0x0F)*4; if (ihl<20 || f.Length<ipOff+ihl) return false;

            if (ip[9]!=6) return false; // TCP

            s=new IPAddress(ip.Slice(12,4)); d=new IPAddress(ip.Slice(16,4));
            int tcpOff=ipOff+ihl; if (f.Length<tcpOff+20) return false;
            var tcp=f.Slice(tcpOff); sp=(ushort)((tcp[0]<<8)|tcp[1]); dp=(ushort)((tcp[2]<<8)|tcp[3]);

            int doff=(tcp[12]>>4)*4; if (doff<20 || f.Length<tcpOff+doff) return false;

            pay=f[(tcpOff + doff)..]; return true;
        }
        
        static int FindHdrEnd(ReadOnlySpan<byte> d)
        { 
            for(int i=0;i+3<d.Length;i++) if (d[i]==13&&d[i+1]==10&&d[i+2]==13&&d[i+3]==10) return i; return -1; 
        
        }
        static int ParseCL(ReadOnlySpan<byte> hdrs)
        {
            var s = System.Text.Encoding.ASCII.GetString(hdrs);
            var i = s.IndexOf("\nContent-Length:", StringComparison.OrdinalIgnoreCase);

            if (i<0) return -1;

            var t = s[(i+16)..]; var nl = t.IndexOf('\n');
            var n = (nl>=0 ? t[..nl] : t).Trim();
            return int.TryParse(n, out var v) ? v : -1;
        }

        static void Ensure(ref byte[] b, int need)
        {
            if (b.Length>=need) return;
            var n = ArrayPool<byte>.Shared.Rent(Math.Max(need, b.Length==0?16384:b.Length*2));
            
            if (b.Length>0) b.AsSpan(0, Math.Min(b.Length,n.Length)).CopyTo(n);
            ArrayPool<byte>.Shared.Return(b); b=n;
        }

        static void Consume(S s, int c)
        {
            if (c<=0) return;
            if (c>=s.L){ s.L=0; return; }

            s.B.AsSpan(c, s.L-c).CopyTo(s.B.AsSpan(0)); s.L-=c;
        }

        // --- parse headers/payload from Ethernet IPv4/TCP frame ---
        if (!TryParse(raw, out var sip, out var sp, out var dip, out var dp, out var tcp))
            throw new ParserStreamNotCompletedException("Not IPv4/TCP or invalid frame");

        if (sp!=80 && dp!=80)
            throw new ParserStreamNotCompletedException("Not HTTP/80 flow");

        var key = K(sip, sp, dip, dp);
        var st  = F.GetOrAdd(key, _ => new S());

        lock (st.K)
        {
            // append payload
            if (!tcp.IsEmpty)
            {
                Ensure(ref st.B, st.L + tcp.Length);
                tcp.CopyTo(st.B.AsSpan(st.L)); st.L += tcp.Length;
            }

            // need headers?
            if (st.H < 0)
            {
                st.H = FindHdrEnd(st.B.AsSpan(0, st.L));
                if (st.H < 0) throw new ParserStreamNotCompletedException("HTTP headers incomplete");
                st.CL = ParseCL(st.B.AsSpan(0, st.H));
                if (st.CL < 0) throw new ParserStreamNotCompletedException("No Content-Length yet");
            }

            // need full body?
            int have = st.L - (st.H + 4);
            if (have < st.CL)
                throw new ParserStreamNotCompletedException($"Body incomplete {have}/{st.CL}");

            // slice tight array for caller
            var body = st.B.AsMemory(st.H + 4, st.CL).ToArray();

            // consume used bytes and reset state for next message
            Consume(st, st.H + 4 + st.CL);
            st.H = -1; st.CL = -1;

            return body;
        }
    }
}