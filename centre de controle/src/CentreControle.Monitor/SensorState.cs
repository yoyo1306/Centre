using System.Drawing;

namespace CentreControle.Monitor;

public sealed class PaletteColors
{
    public Color Label { get; set; } = ColorTranslator.FromHtml("#1FE01F");
    public Color Value { get; set; } = ColorTranslator.FromHtml("#4EC221");
    public Color Graph { get; set; } = ColorTranslator.FromHtml("#56DC23");
    public Color Graph2 { get; set; } = ColorTranslator.FromHtml("#4EC221");
    public Color Grid { get; set; } = ColorTranslator.FromHtml("#008000");
    public Color Frame { get; set; } = ColorTranslator.FromHtml("#005E00");
    public Color Background { get; set; } = Color.Black;

    public static Color Parse(string? hex, Color fallback)
    {
        if (string.IsNullOrWhiteSpace(hex)) return fallback;
        try { return ColorTranslator.FromHtml(hex.Trim()); }
        catch { return fallback; }
    }
}

public sealed class SensorState
{
    public string CpuName { get; set; } = "CPU";
    public string GpuName { get; set; } = "GPU";

    public double CpuUsage { get; set; }
    public double? CpuTemp { get; set; }
    public double GpuUsage { get; set; }
    public double? GpuTemp { get; set; }

    public double RamUsage { get; set; }
    public double RamUsedGb { get; set; }
    public double RamTotalGb { get; set; }

    public double? VramUsage { get; set; }
    public double VramUsedGb { get; set; }
    public double VramTotalGb { get; set; }

    public double DiskUsage { get; set; }
    public double CpuFreqMhz { get; set; }
    public double? GpuPowerW { get; set; }
    public double NetDownMbps { get; set; }
    public double NetUpMbps { get; set; }
    public double UptimeSeconds { get; set; }

    public int IntervalMs { get; set; } = 1000;
    public bool Paused { get; set; }
    public int HistoryCapacity { get; private set; } = 300;
    public int SampleCount { get; private set; }

    public List<double> HistCpu { get; private set; } = new();
    public List<double> HistGpu { get; private set; } = new();
    public List<double?> HistTempCpu { get; private set; } = new();
    public List<double?> HistTempGpu { get; private set; } = new();

    public SensorState(int capacity = 300)
    {
        ResizeHistory(capacity);
    }

    public void ResizeHistory(int newCapacity)
    {
        HistoryCapacity = Math.Max(2, newCapacity);
        HistCpu = ResizeDoubleList(HistCpu, HistoryCapacity, 0.0);
        HistGpu = ResizeDoubleList(HistGpu, HistoryCapacity, 0.0);
        HistTempCpu = ResizeNullableList(HistTempCpu, HistoryCapacity, 40.0);
        HistTempGpu = ResizeNullableList(HistTempGpu, HistoryCapacity, 40.0);
    }

    public void PushSample()
    {
        SampleCount = Math.Min(HistoryCapacity, SampleCount + 1);
        Push(HistCpu, CpuUsage, HistoryCapacity);
        Push(HistGpu, GpuUsage, HistoryCapacity);
        PushNullable(HistTempCpu, CpuTemp ?? (HistTempCpu.Count > 0 ? HistTempCpu[^1] : 40.0), HistoryCapacity);
        PushNullable(HistTempGpu, GpuTemp ?? (HistTempGpu.Count > 0 ? HistTempGpu[^1] : 40.0), HistoryCapacity);
    }

    private static List<double> ResizeDoubleList(List<double> src, int cap, double fill)
    {
        if (src.Count == 0)
            return Enumerable.Repeat(fill, cap).ToList();
        if (src.Count >= cap)
            return src.Skip(src.Count - cap).ToList();
        var pad = Enumerable.Repeat(src[0], cap - src.Count).ToList();
        pad.AddRange(src);
        return pad;
    }

    private static List<double?> ResizeNullableList(List<double?> src, int cap, double? fill)
    {
        if (src.Count == 0)
            return Enumerable.Repeat(fill, cap).ToList();
        if (src.Count >= cap)
            return src.Skip(src.Count - cap).ToList();
        var pad = Enumerable.Repeat(src[0], cap - src.Count).ToList();
        pad.AddRange(src);
        return pad;
    }

    private static void Push(List<double> list, double value, int cap)
    {
        list.Add(value);
        while (list.Count > cap)
            list.RemoveAt(0);
    }

    private static void PushNullable(List<double?> list, double? value, int cap)
    {
        list.Add(value);
        while (list.Count > cap)
            list.RemoveAt(0);
    }

    public string HistorySpanLabel()
    {
        int sec = Math.Max(1, (int)Math.Round(HistoryCapacity * Math.Max(IntervalMs, 1) / 1000.0));
        if (sec >= 60 && sec % 60 == 0)
            return $"{sec / 60} MIN";
        return $"{sec} S";
    }
}
