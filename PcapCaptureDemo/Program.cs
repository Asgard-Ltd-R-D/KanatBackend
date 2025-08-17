using System.Diagnostics;
using SharpPcap;
using SharpPcap.LibPcap;

class Program
{
    static void Main(string[] args)
    {
        // Args: [optional] deviceIndex filterPort
        // Example: dotnet run -- 0 5000
        int deviceIndex = args.Length > 0 ? int.Parse(args[0]) : -1;
        int port = args.Length > 1 ? int.Parse(args[1]) : 5000;

        var devices = CaptureDeviceList.Instance;
        if (devices.Count == 0)
        {
            Console.WriteLine("No capture devices found. Install libpcap/Npcap.");
            return;
        }

        Console.WriteLine("Devices:");
        for (int i = 0; i < devices.Count; i++)
        {
            Console.WriteLine($"[{i}] {devices[i].Name} - {devices[i].Description}");
        }
        if (deviceIndex < 0 || deviceIndex >= devices.Count)
        {
            Console.WriteLine("\nPick device index via arg 0, e.g. `dotnet run -- 0 5000`");
            return;
        }

        // Cast to LibPcapLiveDevice for live capture
        var dev = (LibPcapLiveDevice)devices[deviceIndex];

        // Open device with promiscuous mode
        dev.Open(DeviceModes.Promiscuous);

        // BPF filter: only capture the UDP port we blast to
        dev.Filter = $"udp port {port}";
        Console.WriteLine($"Listening on {dev.Description} with filter: {dev.Filter}");

        long pktCount = 0;
        long byteCount = 0;
        var sw = Stopwatch.StartNew();
        long lastTickMs = sw.ElapsedMilliseconds;

        dev.OnPacketArrival += (s, e) =>
        {
            pktCount++;
            byteCount += e.GetPacket().Data.Length;

            var now = sw.ElapsedMilliseconds;
            if (now - lastTickMs >= 1000)
            {
                var pps = pktCount;
                var mbps = byteCount / (1024.0 * 1024.0);
                Console.WriteLine($"{DateTime.Now:HH:mm:ss}  PPS={pps,7:N0}   MB/s={mbps,6:F2}");
                pktCount = 0;
                byteCount = 0;
                lastTickMs = now;
            }
        };

        dev.StartCapture();
        Console.WriteLine("Press ENTER to stop...");
        Console.ReadLine();
        dev.StopCapture();
        dev.Close();
    }
}
