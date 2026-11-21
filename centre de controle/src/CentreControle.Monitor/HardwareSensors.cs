using System.Diagnostics;
using System.Globalization;
using System.Net.NetworkInformation;
using System.Runtime.InteropServices;
using System.Text;
using CentreControle.Core;
using LibreHardwareMonitor.Hardware;
using Microsoft.Win32;

namespace CentreControle.Monitor;

public sealed class HardwareSensors : IDisposable
{
    private Computer? _lhmComputer;
    private IHardware? _lhmCpu;

    private bool _nvmlReady;
    private IntPtr _nvmlDevice;
    private bool _smiMissing;
    private int _smiCooldown;

    private ulong _prevIdle, _prevKernel, _prevUser;
    private bool _hasPrevCpuTimes;

    private long _prevRxBytes, _prevTxBytes;
    private long _prevNetTick;

    private PerformanceCounter? _diskCounter;

    public string CpuName { get; private set; } = "CPU";
    public string GpuName { get; private set; } = "GPU";

    // ---------- NVML P/Invoke ----------
    [StructLayout(LayoutKind.Sequential)]
    private struct NvmlUtilization
    {
        public uint gpu;
        public uint memory;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct NvmlMemory
    {
        public ulong total;
        public ulong free;
        public ulong used;
    }

    [DllImport("nvml.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern int nvmlInit_v2();

    [DllImport("nvml.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern int nvmlShutdown();

    [DllImport("nvml.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern int nvmlDeviceGetHandleByIndex_v2(uint index, out IntPtr device);

    [DllImport("nvml.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern int nvmlDeviceGetName(IntPtr device, byte[] name, uint length);

    [DllImport("nvml.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern int nvmlDeviceGetTemperature(IntPtr device, uint sensorType, out uint temp);

    [DllImport("nvml.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern int nvmlDeviceGetUtilizationRates(IntPtr device, out NvmlUtilization utilization);

    [DllImport("nvml.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern int nvmlDeviceGetMemoryInfo(IntPtr device, out NvmlMemory memory);

    [DllImport("nvml.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern int nvmlDeviceGetPowerUsage(IntPtr device, out uint powerMilliWatts);

    // ---------- Win32 CPU & RAM ----------
    [StructLayout(LayoutKind.Sequential)]
    private struct FILETIME
    {
        public uint Low;
        public uint High;
        public ulong ToUInt64() => ((ulong)High << 32) | Low;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetSystemTimes(out FILETIME idleTime, out FILETIME kernelTime, out FILETIME userTime);

    [StructLayout(LayoutKind.Sequential)]
    private struct MEMORYSTATUSEX
    {
        public uint dwLength;
        public uint dwMemoryLoad;
        public ulong ullTotalPhys;
        public ulong ullAvailPhys;
        public ulong ullTotalPageFile;
        public ulong ullAvailPageFile;
        public ulong ullTotalVirtual;
        public ulong ullAvailVirtual;
        public ulong ullAvailExtendedVirtual;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GlobalMemoryStatusEx(ref MEMORYSTATUSEX lpBuffer);

    public void Initialize(string libsDir, bool wantCpuTemp)
    {
        // Amorce CPU usage
        ReadCpuUsage();

        // Nom CPU depuis registre en secours rapide
        try
        {
            using var k = Registry.LocalMachine.OpenSubKey(@"HARDWARE\DESCRIPTION\System\CentralProcessor\0");
            var regName = k?.GetValue("ProcessorNameString") as string;
            if (!string.IsNullOrWhiteSpace(regName))
                CpuName = regName.Trim();
        }
        catch { }

        // Init NVML (GPU NVIDIA natif)
        try
        {
            if (nvmlInit_v2() == 0 && nvmlDeviceGetHandleByIndex_v2(0, out _nvmlDevice) == 0)
            {
                var buf = new byte[96];
                if (nvmlDeviceGetName(_nvmlDevice, buf, (uint)buf.Length) == 0)
                {
                    int nul = Array.IndexOf(buf, (byte)0);
                    var n = Encoding.UTF8.GetString(buf, 0, nul >= 0 ? nul : buf.Length).Trim();
                    if (!string.IsNullOrWhiteSpace(n))
                        GpuName = n;
                }
                _nvmlReady = true;
            }
        }
        catch
        {
            _nvmlReady = false;
        }

        // Init LibreHardwareMonitor (CPU temp + horloge) avec auto-installation silencieuse PawnIO
        if (wantCpuTemp)
        {
            try
            {
                PawnIoHelper.EnsureInstalled(libsDir);
                var comp = new Computer
                {
                    IsCpuEnabled = true,
                    IsGpuEnabled = false,
                    IsMemoryEnabled = false,
                    IsMotherboardEnabled = false,
                    IsStorageEnabled = false,
                    IsNetworkEnabled = false,
                    IsBatteryEnabled = false,
                };
                comp.Open();
                _lhmComputer = comp;
                foreach (var hw in comp.Hardware)
                {
                    if (hw.HardwareType == HardwareType.Cpu)
                    {
                        _lhmCpu = hw;
                        if (!string.IsNullOrWhiteSpace(hw.Name))
                            CpuName = hw.Name.Trim();
                        break;
                    }
                }
            }
            catch
            {
                _lhmCpu = null;
            }
        }

        // Disque % (optionnel si compteurs desactives)
        try
        {
            _diskCounter = new PerformanceCounter("PhysicalDisk", "% Disk Time", "_Total", true);
            _ = _diskCounter.NextValue();
        }
        catch
        {
            _diskCounter = null;
        }

        // Amorce reseau
        ReadNetRates();
    }

    public void SampleInto(SensorState s, bool wantCpuTemp)
    {
        s.CpuName = CpuName;
        s.GpuName = GpuName;
        s.CpuUsage = ReadCpuUsage();

        if (wantCpuTemp)
        {
            var (temp, freq) = ReadLhmCpu();
            s.CpuTemp = temp;
            if (freq > 0)
                s.CpuFreqMhz = freq;
        }
        else
        {
            s.CpuTemp = null;
        }

        if (_nvmlReady)
        {
            ReadGpuNvml(s);
        }
        else
        {
            _smiCooldown--;
            if (_smiCooldown <= 0 && !_smiMissing)
            {
                _smiCooldown = 1;
                ReadGpuSmiFallback(s);
            }
        }

        ReadMemory(s);
        s.DiskUsage = ReadDiskUsage();
        var (down, up) = ReadNetRates();
        s.NetDownMbps = down;
        s.NetUpMbps = up;
        s.UptimeSeconds = Environment.TickCount64 / 1000.0;
        s.PushSample();
    }

    private double ReadCpuUsage()
    {
        if (!GetSystemTimes(out var idleFt, out var kernelFt, out var userFt))
            return 0.0;

        ulong idle = idleFt.ToUInt64();
        ulong kernel = kernelFt.ToUInt64();
        ulong user = userFt.ToUInt64();

        if (!_hasPrevCpuTimes)
        {
            _prevIdle = idle;
            _prevKernel = kernel;
            _prevUser = user;
            _hasPrevCpuTimes = true;
            return 0.0;
        }

        ulong dIdle = idle - _prevIdle;
        ulong dKernel = kernel - _prevKernel;
        ulong dUser = user - _prevUser;
        _prevIdle = idle;
        _prevKernel = kernel;
        _prevUser = user;

        ulong total = dKernel + dUser;
        if (total == 0) return 0.0;
        double busy = (double)(total - dIdle) / total * 100.0;
        return Math.Clamp(busy, 0.0, 100.0);
    }

    private (double? TempC, double FreqMhz) ReadLhmCpu()
    {
        if (_lhmCpu is null)
            return (null, 0.0);

        try
        {
            _lhmCpu.Update();
            double? preferredTemp = null;
            double? fallbackTemp = null;
            double maxClock = 0.0;

            foreach (var sensor in _lhmCpu.Sensors)
            {
                if (sensor.Value is null) continue;
                double v = sensor.Value.Value;

                if (sensor.SensorType == SensorType.Temperature && v > 0.5)
                {
                    var name = sensor.Name ?? "";
                    if (preferredTemp is null &&
                        (name.Contains("Tctl", StringComparison.OrdinalIgnoreCase) ||
                         name.Contains("Package", StringComparison.OrdinalIgnoreCase) ||
                         name.Contains("Core", StringComparison.OrdinalIgnoreCase)))
                    {
                        preferredTemp = v;
                    }
                    else if (fallbackTemp is null)
                    {
                        fallbackTemp = v;
                    }
                }
                else if (sensor.SensorType == SensorType.Clock && v > maxClock)
                {
                    var name = sensor.Name ?? "";
                    if (name.Contains("Core", StringComparison.OrdinalIgnoreCase) || maxClock == 0)
                        maxClock = v;
                }
            }

            return (preferredTemp ?? fallbackTemp, maxClock);
        }
        catch
        {
            return (null, 0.0);
        }
    }

    private void ReadGpuNvml(SensorState s)
    {
        try
        {
            if (nvmlDeviceGetTemperature(_nvmlDevice, 0, out var t) == 0)
                s.GpuTemp = t;
            if (nvmlDeviceGetUtilizationRates(_nvmlDevice, out var u) == 0)
                s.GpuUsage = Math.Clamp(u.gpu, 0, 100);
            if (nvmlDeviceGetMemoryInfo(_nvmlDevice, out var mem) == 0 && mem.total > 0)
            {
                s.VramTotalGb = mem.total / (1024.0 * 1024.0 * 1024.0);
                s.VramUsedGb = mem.used / (1024.0 * 1024.0 * 1024.0);
                s.VramUsage = Math.Clamp((double)mem.used / mem.total * 100.0, 0.0, 100.0);
            }
            if (nvmlDeviceGetPowerUsage(_nvmlDevice, out var mw) == 0)
                s.GpuPowerW = mw / 1000.0;
        }
        catch { }
    }

    private void ReadGpuSmiFallback(SensorState s)
    {
        try
        {
            using var p = Process.Start(new ProcessStartInfo
            {
                FileName = "nvidia-smi",
                Arguments = "--query-gpu=name,temperature.gpu,utilization.gpu --format=csv,noheader,nounits",
                CreateNoWindow = true,
                UseShellExecute = false,
                RedirectStandardOutput = true,
            });
            if (p is null) return;
            var line = p.StandardOutput.ReadLine();
            p.WaitForExit(1500);
            if (string.IsNullOrWhiteSpace(line)) return;
            var parts = line.Split(',');
            if (parts.Length >= 3)
            {
                if (!string.IsNullOrWhiteSpace(parts[0]))
                    GpuName = parts[0].Trim();
                if (double.TryParse(parts[1].Trim(), CultureInfo.InvariantCulture, out var gt))
                    s.GpuTemp = gt;
                if (double.TryParse(parts[2].Trim(), CultureInfo.InvariantCulture, out var gu))
                    s.GpuUsage = Math.Clamp(gu, 0.0, 100.0);
            }
        }
        catch (System.ComponentModel.Win32Exception)
        {
            _smiMissing = true;
        }
        catch { }
    }

    private static void ReadMemory(SensorState s)
    {
        var ms = new MEMORYSTATUSEX { dwLength = (uint)Marshal.SizeOf<MEMORYSTATUSEX>() };
        if (!GlobalMemoryStatusEx(ref ms) || ms.ullTotalPhys == 0)
            return;
        ulong used = ms.ullTotalPhys - ms.ullAvailPhys;
        s.RamTotalGb = ms.ullTotalPhys / (1024.0 * 1024.0 * 1024.0);
        s.RamUsedGb = used / (1024.0 * 1024.0 * 1024.0);
        s.RamUsage = Math.Clamp((double)used / ms.ullTotalPhys * 100.0, 0.0, 100.0);
    }

    private double ReadDiskUsage()
    {
        if (_diskCounter is null) return 0.0;
        try
        {
            return Math.Clamp(_diskCounter.NextValue(), 0.0, 100.0);
        }
        catch
        {
            return 0.0;
        }
    }

    private (double DownMbps, double UpMbps) ReadNetRates()
    {
        try
        {
            long rx = 0, tx = 0;
            foreach (var ni in NetworkInterface.GetAllNetworkInterfaces())
            {
                if (ni.OperationalStatus != OperationalStatus.Up ||
                    ni.NetworkInterfaceType == NetworkInterfaceType.Loopback ||
                    ni.NetworkInterfaceType == NetworkInterfaceType.Tunnel)
                    continue;
                var stats = ni.GetIPv4Statistics();
                rx += stats.BytesReceived;
                tx += stats.BytesSent;
            }
            long now = Environment.TickCount64;
            if (_prevNetTick == 0)
            {
                _prevRxBytes = rx;
                _prevTxBytes = tx;
                _prevNetTick = now;
                return (0.0, 0.0);
            }
            double dt = Math.Max(0.1, (now - _prevNetTick) / 1000.0);
            double down = Math.Max(0.0, rx - _prevRxBytes) * 8.0 / 1_000_000.0 / dt;
            double up = Math.Max(0.0, tx - _prevTxBytes) * 8.0 / 1_000_000.0 / dt;
            _prevRxBytes = rx;
            _prevTxBytes = tx;
            _prevNetTick = now;
            return (down, up);
        }
        catch
        {
            return (0.0, 0.0);
        }
    }

    public void Dispose()
    {
        try { _diskCounter?.Dispose(); } catch { }
        try { _lhmComputer?.Close(); } catch { }
        _lhmComputer = null;
        _lhmCpu = null;
        if (_nvmlReady)
        {
            try { nvmlShutdown(); } catch { }
            _nvmlReady = false;
        }
    }
}
