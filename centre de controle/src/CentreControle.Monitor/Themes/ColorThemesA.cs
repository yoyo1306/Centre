using System.Drawing;
using System.Drawing.Drawing2D;
using System.Globalization;

namespace CentreControle.Monitor.Themes;

public sealed class T10Modern : IPanelTheme
{
    public string Key => "10-modern";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        g.Clear(ThemeDrawContext.Hex("#0B0F14"));
        DrawCard(g, ctx, 8, s.CpuName, s.CpuTemp, s.CpuUsage, s.HistCpu, ThemeDrawContext.Hex("#38BDF8"));
        DrawCard(g, ctx, 166, s.GpuName, s.GpuTemp, s.GpuUsage, s.HistGpu, ThemeDrawContext.Hex("#A78BFA"));
    }

    private static void DrawCard(Graphics g, ThemeDrawContext ctx, int top, string name, double? temp, double use, IReadOnlyList<double> hist, Color accent)
    {
        using var cardBg = new SolidBrush(ThemeDrawContext.Hex("#121820"));
        using var cardBorder = new Pen(ThemeDrawContext.Hex("#2A3544"));
        g.FillRectangle(cardBg, 10, top, 460, 146);
        g.DrawRectangle(cardBorder, 10, top, 460, 146);

        ctx.DrawText(g, 26, top + 12, name.ToUpperInvariant(), "Segoe UI", 11, ThemeDrawContext.Hex("#8B98A9"), budget: 300);

        bool hot = temp.HasValue && temp.Value >= 65.0;
        var col = ThemeDrawContext.TempColor(temp, accent);
        using var chipBg = new SolidBrush(ThemeDrawContext.Hex(hot ? "#3A3014" : "#12352C"));
        using var chipBd = new Pen(ThemeDrawContext.Hex(hot ? "#8A6A20" : "#1F6B52"));
        g.FillRectangle(chipBg, 380, top + 10, 72, 18);
        g.DrawRectangle(chipBd, 380, top + 10, 72, 18);
        ctx.DrawText(g, 416, top + 12, hot ? "CHAUD" : "STABLE", "Segoe UI", 9, ThemeDrawContext.Hex(hot ? "#FBBF24" : "#34D399"), TextAnchor.N);

        ctx.DrawText(g, 26, top + 36, temp is null ? "-- °C" : $"{temp.Value:0} °C", "Segoe UI", 36, col, budget: 240);
        ctx.DrawText(g, 26, top + 78, "TEMPÉRATURE", "Segoe UI", 9, ThemeDrawContext.Hex("#566372"));
        ctx.DrawText(g, 452, top + 40, $"{use:0} %", "Segoe UI", 28, ThemeDrawContext.Hex("#E6EDF3"), TextAnchor.NE, budget: 140);
        ctx.DrawText(g, 452, top + 78, "UTILISATION", "Segoe UI", 9, ThemeDrawContext.Hex("#566372"), TextAnchor.NE);

        int sx = 26, sy = top + 96, sw = 424, sh = 28;
        var pts = ThemeDrawContext.BuildLinePoints(hist, sx, sy, sw, sh);
        ThemeDrawContext.DrawSparkArea(g, pts, sy + sh, col, 48);
        if (pts.Length >= 2)
        {
            using var pen = new Pen(col, 2f) { LineJoin = LineJoin.Round };
            g.DrawLines(pen, pts);
        }

        using var barBg = new SolidBrush(ThemeDrawContext.Hex("#1C2630"));
        using var barFg = new SolidBrush(col);
        g.FillRectangle(barBg, sx, top + 130, sw, 4);
        g.FillRectangle(barFg, sx, top + 130, (float)(sw * Math.Clamp(use, 0, 100) / 100.0), 4);
    }
}

public sealed class T11Ambre : IPanelTheme
{
    public string Key => "11-ambre";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        g.Clear(ThemeDrawContext.Hex("#0A0600"));
        using (var scan = new Pen(ThemeDrawContext.Hex("#140C00")))
        {
            for (int y = 0; y < 320; y += 3)
                g.DrawLine(scan, 0, y, 480, y);
        }

        ctx.DrawText(g, 12, 10, "SENSORPANEL // SYS.01", "Consolas", 12, ThemeDrawContext.Hex("#FFB000"), style: FontStyle.Bold, shadow: false);
        ctx.DrawText(g, 468, 10, DateTime.Now.ToString("HH:mm:ss"), "Consolas", 12, ThemeDrawContext.Hex("#FF8F00"), TextAnchor.NE);
        using (var dash = new Pen(ThemeDrawContext.Hex("#FFB000")) { DashPattern = [3f, 3f] })
        {
            g.DrawLine(dash, 12, 30, 468, 30);
            g.DrawLine(dash, 12, 292, 468, 292);
        }

        DrawBlock(g, ctx, 40, s.CpuName, s.CpuTemp, s.CpuUsage, s.HistCpu);
        DrawBlock(g, ctx, 168, s.GpuName, s.GpuTemp, s.GpuUsage, s.HistGpu);

        ctx.DrawText(g, 12, 300, $"● POLL {s.IntervalMs / 1000.0:0.0}s", "Consolas", 10, ThemeDrawContext.Hex("#B36B00"), shadow: false);
        ctx.DrawText(g, 468, 300, "NVML · LHM", "Consolas", 10, ThemeDrawContext.Hex("#B36B00"), TextAnchor.NE, shadow: false);
    }

    private static void DrawBlock(Graphics g, ThemeDrawContext ctx, int top, string name, double? temp, double use, IReadOnlyList<double> hist)
    {
        ctx.DrawText(g, 12, top, "> " + name.ToUpperInvariant(), "Consolas", 11, ThemeDrawContext.Hex("#FFA726"), budget: 450);
        ctx.DrawText(g, 12, top + 18, temp is null ? "-- °C" : $"{temp.Value:0} °C", "Consolas", 28, ThemeDrawContext.Hex("#FFB000"), budget: 220);
        ctx.DrawText(g, 468, top + 18, $"{use:0} %", "Consolas", 28, ThemeDrawContext.Hex("#FFC46B"), TextAnchor.NE, budget: 160);

        int nOn = (int)Math.Round(Math.Clamp(use, 0, 100) / 100.0 * 24.0);
        using var brOn = new SolidBrush(ThemeDrawContext.Hex("#FFB000"));
        using var brOff = new SolidBrush(ThemeDrawContext.Hex("#3A2A08"));
        for (int i = 0; i < 24; i++)
            g.FillRectangle(i < nOn ? brOn : brOff, 12 + i * 19, top + 54, 16, 9);

        var pts = ThemeDrawContext.BuildLinePoints(hist, 12, top + 70, 444, 36);
        if (pts.Length >= 2)
        {
            using var glow = new Pen(ThemeDrawContext.Hex("#7A5800"), 4f) { LineJoin = LineJoin.Round };
            using var line = new Pen(ThemeDrawContext.Hex("#FFB000"), 2f) { LineJoin = LineJoin.Round };
            g.DrawLines(glow, pts);
            g.DrawLines(line, pts);
        }
    }
}

public sealed class T12Minimal : IPanelTheme
{
    public string Key => "12-minimal";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        g.Clear(ThemeDrawContext.Hex("#050505"));
        using (var sep = new Pen(ThemeDrawContext.Hex("#262626")))
            g.DrawLine(sep, 24, 160, 456, 160);

        DrawHalf(g, ctx, 0, s.CpuName, s.CpuTemp, s.CpuUsage, s.HistCpu);
        DrawHalf(g, ctx, 162, s.GpuName, s.GpuTemp, s.GpuUsage, s.HistGpu);
    }

    private static void DrawHalf(Graphics g, ThemeDrawContext ctx, int top, string name, double? temp, double use, IReadOnlyList<double> hist)
    {
        bool hot = temp.HasValue && temp.Value >= 80.0;
        var col = ThemeDrawContext.Hex(hot ? "#FF5C5C" : "#F2F2F2");
        using (var dotBr = new SolidBrush(ThemeDrawContext.Hex(hot ? "#FF5C5C" : "#3A3A3A")))
            g.FillEllipse(dotBr, 24, top + 18, 6, 6);

        ctx.DrawText(g, 24, top + 28, temp is null ? "--" : $"{temp.Value:0}°", "Segoe UI", 52, col, budget: 210);
        ctx.DrawText(g, 24, top + 96, name, "Segoe UI", 11, ThemeDrawContext.Hex("#8F8F8F"), budget: 200);
        ctx.DrawText(g, 24, top + 116, $"USAGE {use:0} %", "Segoe UI", 11, ThemeDrawContext.Hex("#C9C9C9"), budget: 200);

        int sx = 230, sy = top + 22, sw = 226, sh = 96;
        using (var basePen = new Pen(ThemeDrawContext.Hex("#1D1D1D")))
            g.DrawLine(basePen, sx, sy + sh - 8, sx + sw, sy + sh - 8);

        var pts = ThemeDrawContext.BuildLinePoints(hist, sx, sy, sw, sh);
        if (pts.Length >= 2)
        {
            using var pen = new Pen(ThemeDrawContext.Hex("#E8E8E8"), 2f) { LineJoin = LineJoin.Round };
            g.DrawLines(pen, pts);
            var last = pts[^1];
            using var wbr = new SolidBrush(Color.White);
            g.FillEllipse(wbr, last.X - 3f, last.Y - 3f, 6f, 6f);
        }
    }
}

public sealed class T13Neon : IPanelTheme
{
    public string Key => "13-neon";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        g.Clear(ThemeDrawContext.Hex("#0A0022"));
        using (var bg2 = new SolidBrush(ThemeDrawContext.Hex("#14042E")))
            g.FillRectangle(bg2, 0, 220, 480, 100);
        using (var py = new Pen(ThemeDrawContext.Hex("#3A1460")))
        {
            for (int y = 230; y < 320; y += 14) g.DrawLine(py, 0, y, 480, y);
        }
        using (var px = new Pen(ThemeDrawContext.Hex("#401030")))
        {
            for (int x = 0; x < 480; x += 26) g.DrawLine(px, x, 240, x, 320);
        }

        ctx.DrawText(g, 14, 10, "⌁ SENSOR PANEL", "Segoe UI", 12, ThemeDrawContext.Hex("#00E5FF"));
        ctx.DrawText(g, 466, 10, DateTime.Now.ToString("HH:mm"), "Segoe UI", 12, ThemeDrawContext.Hex("#FF3EC8"), TextAnchor.NE);

        DrawPanel(g, ctx, 38, "CPU · " + s.CpuName, s.CpuTemp, s.CpuUsage, ThemeDrawContext.Hex("#00E5FF"), ThemeDrawContext.Hex("#7FF3FF"));
        DrawPanel(g, ctx, 174, "GPU · " + s.GpuName, s.GpuTemp, s.GpuUsage, ThemeDrawContext.Hex("#FF3EC8"), ThemeDrawContext.Hex("#FFA8EA"));
    }

    private static void DrawPanel(Graphics g, ThemeDrawContext ctx, int top, string name, double? temp, double use, Color accent, Color edge)
    {
        using var bg = new SolidBrush(ThemeDrawContext.Hex("#12082E"));
        using var bd = new Pen(accent, 2f);
        g.FillRectangle(bg, 12, top, 456, 126);
        g.DrawRectangle(bd, 12, top, 456, 126);

        ctx.DrawText(g, 26, top + 10, name.ToUpperInvariant(), "Segoe UI", 10, edge, budget: 420);
        ctx.DrawText(g, 26, top + 32, temp is null ? "--°C" : $"{temp.Value:0}°C", "Segoe UI", 36, accent, style: FontStyle.Bold | FontStyle.Italic);
        ctx.DrawText(g, 454, top + 36, $"{use:0}%", "Segoe UI", 30, ThemeDrawContext.Hex("#E8ECFF"), TextAnchor.NE, style: FontStyle.Bold | FontStyle.Italic);
        ctx.DrawText(g, 26, top + 74, "TEMPÉRATURE", "Segoe UI", 8, ThemeDrawContext.Hex("#7780B8"));
        ctx.DrawText(g, 454, top + 74, "UTILISATION", "Segoe UI", 8, ThemeDrawContext.Hex("#7780B8"), TextAnchor.NE);

        int nOn = (int)Math.Round(Math.Clamp(use, 0, 100) / 100.0 * 22.0);
        using var on = new SolidBrush(accent);
        using var off = new SolidBrush(ThemeDrawContext.Hex("#2A2048"));
        for (int i = 0; i < 22; i++)
            g.FillRectangle(i < nOn ? on : off, 26 + i * 20, top + 100, 16, 10);
    }
}

public sealed class T14Flux : IPanelTheme
{
    public string Key => "14-flux";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        g.Clear(ThemeDrawContext.Hex("#08120E"));
        using (var grid = new Pen(ThemeDrawContext.Hex("#0E1C16")))
        {
            for (int x = 0; x < 480; x += 24) g.DrawLine(grid, x, 0, x, 320);
        }
        using (var ring = new Pen(ThemeDrawContext.Hex("#163228")))
        {
            foreach (int r in new[] { 48, 96, 150 })
                g.DrawEllipse(ring, 400 - r, -30 - r, r * 2, r * 2);
        }

        ctx.DrawText(g, 14, 8, "FLUX", "Segoe UI", 13, ThemeDrawContext.Hex("#D7F5E4"));
        ctx.DrawText(g, 240, 10, ThemeDrawContext.UptimeStr(s.UptimeSeconds), "Segoe UI", 11, ThemeDrawContext.Hex("#8FB8A4"), TextAnchor.N);
        ctx.DrawText(g, 466, 8, DateTime.Now.ToString("HH:mm"), "Segoe UI", 13, ThemeDrawContext.Hex("#F0C14A"), TextAnchor.NE);

        DrawMainCard(g, ctx, 10, "CPU", s.CpuName, s.CpuTemp, s.CpuUsage, s.HistCpu, ThemeDrawContext.Hex("#5EE0A0"));
        DrawMainCard(g, ctx, 246, "GPU", s.GpuName, s.GpuTemp, s.GpuUsage, s.HistGpu, ThemeDrawContext.Hex("#F0C14A"));

        DrawRow(g, ctx, 198, "MÉMOIRE", ThemeDrawContext.Hex("#7EC8E3"), s.RamUsage, $"{s.RamUsage:0}%",
            $"{ThemeDrawContext.GoStr(s.RamUsedGb)} / {ThemeDrawContext.GoStr(s.RamTotalGb)} Go");
        DrawRow(g, ctx, 222, "VRAM", ThemeDrawContext.Hex("#C9B6E4"), s.VramUsage ?? 0.0,
            s.VramUsage is null ? "--%" : $"{s.VramUsage.Value:0}%",
            s.VramUsage is null ? "--" : $"{ThemeDrawContext.GoStr(s.VramUsedGb)} / {ThemeDrawContext.GoStr(s.VramTotalGb)} Go");
        DrawRow(g, ctx, 246, "DISQUE", ThemeDrawContext.Hex("#E07A5F"), s.DiskUsage, $"{s.DiskUsage:0}%", "");

        using (var sep = new Pen(ThemeDrawContext.Hex("#1C3A2E")))
            g.DrawLine(sep, 14, 270, 466, 270);

        DrawBit(g, ctx, 14, "FRÉQUENCE", s.CpuFreqMhz <= 0 ? "--" : $"{(s.CpuFreqMhz / 1000.0).ToString("0.0", CultureInfo.InvariantCulture)} GHz");
        DrawBit(g, ctx, 132, "PUISSANCE", s.GpuPowerW is null ? "--" : $"{s.GpuPowerW.Value:0} W");
        DrawBit(g, ctx, 250, "↓ Mbit/s", ThemeDrawContext.RateStr(s.NetDownMbps));
        DrawBit(g, ctx, 366, "↑ Mbit/s", ThemeDrawContext.RateStr(s.NetUpMbps));
    }

    private static void DrawMainCard(Graphics g, ThemeDrawContext ctx, int left, string title, string name, double? temp, double use, IReadOnlyList<double> hist, Color accent)
    {
        using var bg = new SolidBrush(ThemeDrawContext.Hex("#0E1C16"));
        using var bd = new Pen(ThemeDrawContext.Hex("#1C3A2E"));
        g.FillRectangle(bg, left, 34, 224, 152);
        g.DrawRectangle(bd, left, 34, 224, 152);

        ctx.DrawText(g, left + 12, 42, title, "Segoe UI", 10, accent);
        ctx.DrawText(g, left + 12, 58, ctx.ShortSuffix(g, name, "Segoe UI", 9, 198), "Segoe UI", 9, ThemeDrawContext.Hex("#8AA399"), budget: 198);
        ctx.DrawText(g, left + 12, 76, temp is null ? "--°" : $"{temp.Value:0}°", "Segoe UI", 34, ThemeDrawContext.Hex("#F4F7F2"), budget: 130);
        ctx.DrawText(g, left + 210, 86, $"{use:0}%", "Segoe UI", 16, accent, TextAnchor.NE, budget: 70);

        using var barBg = new SolidBrush(ThemeDrawContext.Hex("#13241C"));
        using var barFg = new SolidBrush(accent);
        g.FillRectangle(barBg, left + 12, 124, 198, 8);
        g.FillRectangle(barFg, left + 12, 124, (float)(198.0 * Math.Clamp(use, 0, 100) / 100.0), 8);

        var pts = ThemeDrawContext.BuildLinePoints(hist, left + 12, 140, 198, 34);
        if (pts.Length >= 2)
        {
            using var pen = new Pen(accent, 2f) { LineJoin = LineJoin.Round };
            g.DrawLines(pen, pts);
        }
    }

    private static void DrawRow(Graphics g, ThemeDrawContext ctx, int y, string label, Color color, double pct, string pctText, string detail)
    {
        ctx.DrawText(g, 14, y, label, "Segoe UI", 10, color, budget: 78);
        ctx.DrawText(g, 98, y, pctText, "Segoe UI", 12, ThemeDrawContext.Hex("#F4F7F2"), budget: 52);
        using var bg = new SolidBrush(ThemeDrawContext.Hex("#13241C"));
        using var fg = new SolidBrush(color);
        g.FillRectangle(bg, 156, y + 4, 176, 8);
        g.FillRectangle(fg, 156, y + 4, (float)(176.0 * Math.Clamp(pct, 0, 100) / 100.0), 8);
        ctx.DrawText(g, 340, y, detail, "Segoe UI", 10, ThemeDrawContext.Hex("#A8BDB2"), budget: 126);
    }

    private static void DrawBit(Graphics g, ThemeDrawContext ctx, int x, string label, string val)
    {
        ctx.DrawText(g, x, 276, label, "Segoe UI", 8, ThemeDrawContext.Hex("#7E9488"));
        ctx.DrawText(g, x, 290, val, "Segoe UI", 14, ThemeDrawContext.Hex("#F4F7F2"), budget: 108);
    }
}

public sealed class T15Atelier : IPanelTheme
{
    public string Key => "15-atelier";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        g.Clear(ThemeDrawContext.Hex("#211612"));
        using (var p2 = new Pen(ThemeDrawContext.Hex("#3A2822"), 2f))
        {
            g.DrawEllipse(p2, -90, 170, 320, 320);
            g.DrawEllipse(p2, 280, -80, 280, 280);
        }
        using (var p1 = new Pen(ThemeDrawContext.Hex("#2E201C")))
            g.DrawEllipse(p1, 150, 70, 210, 210);
        using (var diag = new Pen(ThemeDrawContext.Hex("#3A2A24")))
        {
            for (int x = -40; x < 480; x += 14) g.DrawLine(diag, x, 0, x + 28, 46);
        }

        ctx.DrawText(g, 14, 6, DateTime.Now.ToString("HH:mm"), "Segoe UI", 22, ThemeDrawContext.Hex("#F8EFE6"));
        ctx.DrawText(g, 148, 14, "ATELIER", "Segoe UI", 11, ThemeDrawContext.Hex("#E7A07A"));
        ctx.DrawText(g, 466, 14, ThemeDrawContext.UptimeStr(s.UptimeSeconds), "Segoe UI", 11, ThemeDrawContext.Hex("#C4A090"), TextAnchor.NE);

        var tiles = new (string Label, string Val, double Frac, string Accent)[]
        {
            ("TEMPÉRATURE CPU", s.CpuTemp is null ? "--°" : $"{s.CpuTemp.Value:0}°", (s.CpuTemp ?? 0) / 100.0, "#E8896A"),
            ("CHARGE CPU", $"{s.CpuUsage:0}%", s.CpuUsage / 100.0, "#E6C27A"),
            ("FRÉQUENCE", s.CpuFreqMhz <= 0 ? "--" : $"{(s.CpuFreqMhz / 1000.0).ToString("0.0", CultureInfo.InvariantCulture)} GHz", Math.Min(s.CpuFreqMhz / 1000.0, 6.0) / 6.0, "#D7C4A1"),
            ("TEMPÉRATURE GPU", s.GpuTemp is null ? "--°" : $"{s.GpuTemp.Value:0}°", (s.GpuTemp ?? 0) / 100.0, "#8FB8C4"),
            ("CHARGE GPU", $"{s.GpuUsage:0}%", s.GpuUsage / 100.0, "#CDB4E0"),
            ("PUISSANCE GPU", s.GpuPowerW is null ? "--" : $"{s.GpuPowerW.Value:0} W", Math.Min(s.GpuPowerW ?? 0, 400.0) / 400.0, "#F0A48A"),
        };

        using var tileBg = new SolidBrush(ThemeDrawContext.Hex("#2C211C"));
        using var trackBg = new SolidBrush(ThemeDrawContext.Hex("#3A2C26"));
        for (int i = 0; i < tiles.Length; i++)
        {
            int col = i % 3, row = i / 3;
            int x = 10 + col * 156, y = 50 + row * 104;
            var accent = ThemeDrawContext.Hex(tiles[i].Accent);
            using var bd = new Pen(accent);
            g.FillRectangle(tileBg, x, y, 148, 96);
            g.DrawRectangle(bd, x, y, 148, 96);
            ctx.DrawText(g, x + 10, y + 8, tiles[i].Label, "Segoe UI", 8, ThemeDrawContext.Hex("#C4A090"), budget: 128);
            ctx.DrawText(g, x + 10, y + 28, tiles[i].Val, "Segoe UI", 22, accent, budget: 128);
            g.FillRectangle(trackBg, x + 10, y + 74, 128, 8);
            using var fg = new SolidBrush(accent);
            g.FillRectangle(fg, x + 10, y + 74, (float)(128.0 * Math.Clamp(tiles[i].Frac, 0, 1)), 8);
        }

        using var footBg = new SolidBrush(ThemeDrawContext.Hex("#2A1C18"));
        using var footBd = new Pen(ThemeDrawContext.Hex("#3A2822"));
        g.FillRectangle(footBg, 10, 262, 460, 48);
        g.DrawRectangle(footBd, 10, 262, 460, 48);

        var feet = new (string Label, string Val, double? Frac, string Color)[]
        {
            ("MÉMOIRE", $"{s.RamUsage:0}%  {ThemeDrawContext.GoStr(s.RamUsedGb)} Go", s.RamUsage / 100.0, "#E6C27A"),
            ("VRAM", s.VramUsage is null ? "--" : $"{s.VramUsage.Value:0}%  {ThemeDrawContext.GoStr(s.VramUsedGb)} Go", (s.VramUsage ?? 0) / 100.0, "#CDB4E0"),
            ("DISQUE", $"{s.DiskUsage:0}%", s.DiskUsage / 100.0, "#E8896A"),
            ("Mbit/s", $"↓{ThemeDrawContext.RateStr(s.NetDownMbps)}  ↑{ThemeDrawContext.RateStr(s.NetUpMbps)}", null, "#8FB8C4"),
        };

        for (int i = 0; i < feet.Length; i++)
        {
            int x = 20 + i * 116;
            var c = ThemeDrawContext.Hex(feet[i].Color);
            ctx.DrawText(g, x, 268, feet[i].Label, "Segoe UI", 8, c, budget: 100);
            ctx.DrawText(g, x, 282, feet[i].Val, "Segoe UI", 12, ThemeDrawContext.Hex("#F8EFE6"), budget: 108);
            if (feet[i].Frac is double footFrac)
            {
                g.FillRectangle(trackBg, x, 300, 96, 6);
                using var fg = new SolidBrush(c);
                g.FillRectangle(fg, x, 300, (float)(96.0 * Math.Clamp(footFrac, 0, 1)), 6);
            }
        }
    }
}
