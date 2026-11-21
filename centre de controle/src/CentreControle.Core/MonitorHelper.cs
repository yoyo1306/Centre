using System.Runtime.InteropServices;

namespace CentreControle.Core;

public readonly record struct MonitorRect(IntPtr Handle, int X, int Y, int Width, int Height);

public static class MonitorHelper
{
    [StructLayout(LayoutKind.Sequential)]
    private struct RECT
    {
        public int Left, Top, Right, Bottom;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct PHYSICAL_MONITOR
    {
        public IntPtr hPhysicalMonitor;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string szPhysicalMonitorDescription;
    }

    private delegate bool MonitorEnumProc(IntPtr hMonitor, IntPtr hdcMonitor, ref RECT lprcMonitor, IntPtr dwData);

    [DllImport("user32.dll")]
    private static extern bool EnumDisplayMonitors(IntPtr hdc, IntPtr lprcClip, MonitorEnumProc lpfnEnum, IntPtr dwData);

    [DllImport("user32.dll")]
    private static extern int GetSystemMetrics(int nIndex);

    [DllImport("dxva2.dll", SetLastError = true)]
    private static extern bool GetNumberOfPhysicalMonitorsFromHMONITOR(IntPtr hMonitor, out uint pdwNumberOfPhysicalMonitors);

    [DllImport("dxva2.dll", SetLastError = true)]
    private static extern bool GetPhysicalMonitorsFromHMONITOR(IntPtr hMonitor, uint dwPhysicalMonitorArraySize, [Out] PHYSICAL_MONITOR[] pPhysicalMonitorArray);

    [DllImport("dxva2.dll", SetLastError = true)]
    private static extern bool DestroyPhysicalMonitors(uint dwPhysicalMonitorArraySize, [In] PHYSICAL_MONITOR[] pPhysicalMonitorArray);

    [DllImport("dxva2.dll", SetLastError = true)]
    private static extern bool GetVCPFeatureAndVCPFeatureReply(IntPtr hMonitor, byte bVCPCode, out uint pvct, out uint pdwCurrentValue, out uint pdwMaximumValue);

    [DllImport("dxva2.dll", SetLastError = true)]
    private static extern bool SetMonitorBrightness(IntPtr hMonitor, uint dwNewBrightness);

    [DllImport("dxva2.dll", SetLastError = true)]
    private static extern bool SetVCPFeature(IntPtr hMonitor, byte bVCPCode, uint dwNewValue);

    public static List<MonitorRect> GetAllMonitors()
    {
        var list = new List<MonitorRect>();
        try
        {
            EnumDisplayMonitors(IntPtr.Zero, IntPtr.Zero, (IntPtr hMon, IntPtr _, ref RECT rc, IntPtr _) =>
            {
                list.Add(new MonitorRect(hMon, rc.Left, rc.Top, rc.Right - rc.Left, rc.Bottom - rc.Top));
                return true;
            }, IntPtr.Zero);
        }
        catch { }
        return list;
    }

    public static (int Width, int Height) GetPrimarySize()
    {
        try
        {
            int w = GetSystemMetrics(0);
            int h = GetSystemMetrics(1);
            if (w > 0 && h > 0)
                return (w, h);
        }
        catch { }
        return (1920, 1080);
    }

    public static (int X, int Y, string Label) GetCenteredPanelPosition()
    {
        var mons = GetAllMonitors();
        var exact = mons.FirstOrDefault(m => m.Width == ThemeCatalog.PanelWidth && m.Height == ThemeCatalog.PanelHeight);
        if (exact.Handle != IntPtr.Zero)
            return (exact.X, exact.Y, "Moniteur recentré (petit écran 480×320)");

        if (mons.Count > 0)
        {
            var smallest = mons.OrderBy(m => (long)m.Width * m.Height).First();
            int tx = smallest.X + (smallest.Width - ThemeCatalog.PanelWidth) / 2;
            int ty = smallest.Y + (smallest.Height - ThemeCatalog.PanelHeight) / 2;
            var label = mons.Count > 1
                ? "Moniteur recentré (plus petit écran)"
                : "Moniteur recentré (écran principal)";
            return (tx, ty, label);
        }

        var (pw, ph) = GetPrimarySize();
        return ((pw - ThemeCatalog.PanelWidth) / 2, (ph - ThemeCatalog.PanelHeight) / 2, "Moniteur recentré (écran principal)");
    }

    private static T? WithSmallPhysicalMonitor<T>(Func<IntPtr, T> action)
    {
        foreach (var m in GetAllMonitors())
        {
            if (m.Width != ThemeCatalog.PanelWidth || m.Height != ThemeCatalog.PanelHeight)
                continue;
            if (!GetNumberOfPhysicalMonitorsFromHMONITOR(m.Handle, out var count) || count == 0)
                return default;
            var arr = new PHYSICAL_MONITOR[count];
            if (!GetPhysicalMonitorsFromHMONITOR(m.Handle, count, arr))
                return default;
            try
            {
                return action(arr[0].hPhysicalMonitor);
            }
            finally
            {
                DestroyPhysicalMonitors(count, arr);
            }
        }
        return default;
    }

    public static bool HasSmallMonitor()
        => GetAllMonitors().Any(m => m.Width == ThemeCatalog.PanelWidth && m.Height == ThemeCatalog.PanelHeight);

    public static int? ReadSmallBrightness()
    {
        return WithSmallPhysicalMonitor<int?>(handle =>
        {
            if (GetVCPFeatureAndVCPFeatureReply(handle, 0x10, out _, out var cur, out _))
                return (int)cur;
            return null;
        });
    }

    public static bool ApplySmallBrightness(int percent)
    {
        uint val = (uint)Math.Clamp(percent, 0, 100);
        return WithSmallPhysicalMonitor<bool>(handle =>
            SetMonitorBrightness(handle, val) || SetVCPFeature(handle, 0x10, val));
    }
}
