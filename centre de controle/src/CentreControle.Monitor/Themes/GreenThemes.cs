using System.Drawing;
using System.Drawing.Drawing2D;

namespace CentreControle.Monitor.Themes;

internal static class GreenFont
{
    public const string Family = "Dash Digital-7";
}

public sealed class T01AidaPlus : IPanelTheme
{
    public string Key => "01-aida";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        var C = ctx.Colors;
        ctx.DrawGreenBackground(g);

        var boxes = new[] { (0, 40, 479, 119), (0, 200, 479, 119) };
        using var gridPen = new Pen(C.Grid, 1f);
        foreach (var (x, y, w, h) in boxes)
            ThemeDrawContext.DrawCrispRect(g, gridPen, x, y, w, h);

        ctx.DrawText(g, 10, 13, s.CpuName, GreenFont.Family, 13, C.Label, TextAnchor.NW, budget: 360, shadow: false);
        ctx.DrawText(g, 474, 13, ThemeDrawContext.TempInt(s.CpuTemp), GreenFont.Family, 13, C.Label, TextAnchor.NE, budget: 96, sample: "100°C", shadow: false);
        ctx.DrawText(g, 10, 173, s.GpuName, GreenFont.Family, 13, C.Label, TextAnchor.NW, budget: 360, shadow: false);
        ctx.DrawText(g, 474, 173, ThemeDrawContext.TempInt(s.GpuTemp), GreenFont.Family, 13, C.Label, TextAnchor.NE, budget: 96, sample: "100°C", shadow: false);

        DrawAidaSpark(g, s.HistCpu, s.SampleCount, 1, 42, 477, 115, C.Graph);
        DrawAidaSpark(g, s.HistGpu, s.SampleCount, 1, 202, 477, 115, C.Graph2);
    }

    private static void DrawAidaSpark(Graphics g, IReadOnlyList<double> hist, int sampleCount, float x, float y, float w, float h, Color col)
    {
        int n = hist.Count;
        if (n < 2 || sampleCount <= 0) return;

        int active = Math.Min(sampleCount, n);
        int startIdx = n - active;
        float step = w / (n - 1);

        if (active == 1)
        {
            double frac = Math.Clamp(hist[^1], 0.0, 100.0) / 100.0;
            float py = y + h - (float)(frac * h);
            using var pen1 = new Pen(col, 2f);
            g.DrawLine(pen1, x + w - Math.Max(2f, step), py, x + w, py);
            return;
        }

        var pts = new PointF[active];
        for (int i = 0; i < active; i++)
        {
            int idx = startIdx + i;
            double frac = Math.Clamp(hist[idx], 0.0, 100.0) / 100.0;
            pts[i] = new PointF(x + idx * step, y + h - (float)(frac * h));
        }
        using var pen = new Pen(col, 2f) { LineJoin = LineJoin.Round };
        g.DrawLines(pen, pts);
    }

    internal static void DrawSpark(Graphics g, IReadOnlyList<double> hist, float x, float y, float w, float h, Color col, bool dashed = false)
    {
        var pts = ThemeDrawContext.BuildLinePoints(hist, x, y, w, h);
        if (pts.Length < 2) return;
        using var pen = new Pen(col, 2f) { LineJoin = LineJoin.Round };
        if (dashed) pen.DashPattern = [5f, 4f];
        g.DrawLines(pen, pts);
    }
}

public sealed class T02Hud : IPanelTheme
{
    public string Key => "02-hud";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        var C = ctx.Colors;
        ctx.DrawGreenBackground(g);

        using var framePen = new Pen(C.Frame, 1f);
        using var gridPen = new Pen(C.Grid, 1f);
        g.DrawLine(framePen, 240, 8, 240, 312);

        DrawHalf(g, ctx, 0, s.CpuName, s.CpuTemp, s.CpuUsage, s.HistCpu, C.Graph, gridPen);
        DrawHalf(g, ctx, 240, s.GpuName, s.GpuTemp, s.GpuUsage, s.HistGpu, C.Graph2, gridPen);
    }

    private static void DrawHalf(Graphics g, ThemeDrawContext ctx, int ox, string name, double? temp, double use, IReadOnlyList<double> hist, Color col, Pen gridPen)
    {
        var C = ctx.Colors;
        int cx = ox + 120;
        ctx.DrawText(g, cx, 10, name, GreenFont.Family, 13, C.Label, TextAnchor.N, budget: 216);
        ctx.DrawText(g, cx, 42, ThemeDrawContext.TempInt(temp), GreenFont.Family, 34, C.Value, TextAnchor.N, budget: 208, sample: "100°C");
        ctx.DrawText(g, ox + 16, 112, "CHARGE", GreenFont.Family, 10, C.Grid, TextAnchor.NW, shadow: false);
        ctx.DrawText(g, ox + 224, 106, $"{use:0} %", GreenFont.Family, 18, C.Label, TextAnchor.NE, budget: 110, sample: "100 %");

        int bx = ox + 16, bw = 208, by = 138;
        g.DrawRectangle(gridPen, bx, by, bw, 9);
        float fillW = (float)((bw - 2) * Math.Clamp(use, 0, 100) / 100.0);
        if (fillW > 0.5f)
        {
            using var br = new SolidBrush(col);
            g.FillRectangle(br, bx + 1, by + 1, fillW, 7);
        }

        int sx = ox + 16, sw = 208, sy = 166, sh = 138;
        g.DrawRectangle(gridPen, sx, sy, sw, sh);
        T01AidaPlus.DrawSpark(g, hist, sx + 1, sy + 1, sw - 2, sh - 2, col);
    }
}

public sealed class T03Anneaux : IPanelTheme
{
    public string Key => "03-anneaux";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        var C = ctx.Colors;
        ctx.DrawGreenBackground(g);
        using var tickPen = new Pen(C.Grid, 2f);
        using var gridPen = new Pen(C.Grid, 1f);

        DrawGauge(g, ctx, 120, "CPU", s.CpuName, s.CpuTemp, s.CpuUsage, C.Graph, tickPen);
        DrawGauge(g, ctx, 360, "GPU", s.GpuName, s.GpuTemp, s.GpuUsage, C.Graph2, tickPen);

        DrawBox(g, ctx, 12, "CPU", s.HistCpu, C.Graph, gridPen);
        DrawBox(g, ctx, 252, "GPU", s.HistGpu, C.Graph2, gridPen);
    }

    private static void DrawGauge(Graphics g, ThemeDrawContext ctx, float cx, string tag, string name, double? temp, double use, Color col, Pen tickPen)
    {
        var C = ctx.Colors;
        float r = 68f, cy = 108f;
        ThemeDrawContext.DrawCompassArc(g, cx, cy, r, -120f, 120f, C.Frame, 8f);
        float sweepEnd = -120f + (float)(240.0 * Math.Clamp(use, 0, 100) / 100.0);
        ThemeDrawContext.DrawCompassArc(g, cx, cy, r, -120f, sweepEnd, col, 8f);

        foreach (var deg in new[] { -120, -60, 0, 60, 120 })
        {
            var p0 = ThemeDrawContext.Compass(cx, cy, r + 8f, deg);
            var p1 = ThemeDrawContext.Compass(cx, cy, r + 13f, deg);
            g.DrawLine(tickPen, p0, p1);
        }

        ctx.DrawText(g, cx, 10, name, GreenFont.Family, 12, C.Label, TextAnchor.N, budget: 216);
        ctx.DrawText(g, cx, 82, ThemeDrawContext.TempInt(temp), GreenFont.Family, 24, C.Value, TextAnchor.N, budget: 114, sample: "100°C");
        ctx.DrawText(g, cx, 118, $"{tag} · {use:0} %", GreenFont.Family, 13, C.Label, TextAnchor.N, budget: 106, sample: $"{tag} · 100 %");
    }

    private static void DrawBox(Graphics g, ThemeDrawContext ctx, int sx, string tag, IReadOnlyList<double> hist, Color col, Pen gridPen)
    {
        int sy = 204, sw = 216, sh = 104;
        ctx.DrawText(g, sx + 2, 188, tag, GreenFont.Family, 9, ctx.Colors.Grid, TextAnchor.NW, shadow: false);
        g.DrawRectangle(gridPen, sx, sy, sw, sh);
        T01AidaPlus.DrawSpark(g, hist, sx + 1, sy + 1, sw - 2, sh - 2, col);
    }
}

public sealed class T04Tuiles : IPanelTheme
{
    public string Key => "04-tuiles";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        var C = ctx.Colors;
        ctx.DrawGreenBackground(g);
        using var gridPen = new Pen(C.Grid, 1f);
        using var framePen = new Pen(C.Frame, 1f);

        var htc = s.HistTempCpu.Select(v => v ?? 40.0).ToList();
        var htg = s.HistTempGpu.Select(v => v ?? 40.0).ToList();

        DrawTile(g, ctx, 6, 6, 228, 148, "CPU · TEMPÉRATURE", ThemeDrawContext.TempInt(s.CpuTemp), "100°C", htc, C.Graph, gridPen, framePen);
        DrawTile(g, ctx, 246, 6, 228, 148, "CPU · CHARGE", $"{s.CpuUsage:0} %", "100 %", s.HistCpu, C.Graph, gridPen, framePen);
        DrawTile(g, ctx, 6, 166, 228, 148, "GPU · TEMPÉRATURE", ThemeDrawContext.TempInt(s.GpuTemp), "100°C", htg, C.Graph2, gridPen, framePen);
        DrawTile(g, ctx, 246, 166, 228, 148, "GPU · CHARGE", $"{s.GpuUsage:0} %", "100 %", s.HistGpu, C.Graph2, gridPen, framePen);
    }

    private static void DrawTile(Graphics g, ThemeDrawContext ctx, int x, int y, int w, int h, string label, string val, string sample, IReadOnlyList<double> hist, Color col, Pen gridPen, Pen framePen)
    {
        var C = ctx.Colors;
        g.DrawRectangle(gridPen, x, y, w, h);
        int sx = x + 12, sy = y + 88, sw = w - 24, sh = 50;
        g.DrawRectangle(framePen, sx, sy, sw, sh);
        T01AidaPlus.DrawSpark(g, hist, sx + 1, sy + 1, sw - 2, sh - 2, col);
        ctx.DrawText(g, x + 12, y + 10, label, GreenFont.Family, 10, C.Grid);
        ctx.DrawText(g, x + 12, y + 32, val, GreenFont.Family, 32, C.Value, budget: w - 24, sample: sample);
    }
}

public sealed class T05Colonnes : IPanelTheme
{
    public string Key => "05-colonnes";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        var C = ctx.Colors;
        ctx.DrawGreenBackground(g);
        using var framePen = new Pen(C.Frame, 1f);
        using var gridPen = new Pen(C.Grid, 1f);
        g.DrawLine(framePen, 240, 8, 240, 312);

        DrawCol(g, ctx, 0, s.CpuName, s.CpuTemp, s.CpuUsage, s.HistCpu, C.Graph, gridPen);
        DrawCol(g, ctx, 240, s.GpuName, s.GpuTemp, s.GpuUsage, s.HistGpu, C.Graph2, gridPen);
    }

    private static void DrawCol(Graphics g, ThemeDrawContext ctx, int ox, string name, double? temp, double use, IReadOnlyList<double> hist, Color col, Pen gridPen)
    {
        var C = ctx.Colors;
        const int segs = 14, segH = 15, segGap = 3, segTop = 38;
        int cx = ox + 196;
        double level = segs * Math.Clamp(use, 0, 100) / 100.0;

        for (int i = 0; i < segs; i++)
        {
            int yy = segTop + (segs - 1 - i) * (segH + segGap);
            double op = Math.Clamp(level - i, 0.0, 1.0);
            if (op > 0.08)
            {
                using var br = new SolidBrush(Color.FromArgb((int)(op * 255), col));
                g.FillRectangle(br, cx + 1, yy + 1, 27, segH - 1);
            }
            g.DrawRectangle(gridPen, cx, yy, 28, segH);
        }

        int sx = ox + 14, sy = 142, sw = 170, sh = 162;
        g.DrawRectangle(gridPen, sx, sy, sw, sh);
        T01AidaPlus.DrawSpark(g, hist, sx + 1, sy + 1, sw - 2, sh - 2, col);

        ctx.DrawText(g, ox + 14, 10, name, GreenFont.Family, 12, C.Label, budget: 212);
        ctx.DrawText(g, ox + 14, 38, ThemeDrawContext.TempInt(temp), GreenFont.Family, 26, C.Value, budget: 172, sample: "100°C");
        ctx.DrawText(g, ox + 14, 78, $"{use:0} %", GreenFont.Family, 26, col, budget: 172, sample: "100 %");
        ctx.DrawText(g, ox + 14, 118, "CHARGE", GreenFont.Family, 9, C.Grid);
    }
}

public sealed class T06Oscillo : IPanelTheme
{
    public string Key => "06-oscillo";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        var C = ctx.Colors;
        ctx.DrawGreenBackground(g);
        using var gridPen = new Pen(C.Grid, 1f);
        using var framePen = new Pen(C.Frame, 1f);

        int gx = 10, gy = 24, gw = 460, gh = 164;
        g.DrawRectangle(gridPen, gx, gy, gw, gh);
        g.DrawLine(framePen, gx, gy + gh / 2f, gx + gw, gy + gh / 2f);

        T01AidaPlus.DrawSpark(g, s.HistCpu, gx + 1, gy + 1, gw - 2, gh - 2, C.Graph, dashed: false);
        T01AidaPlus.DrawSpark(g, s.HistGpu, gx + 1, gy + 1, gw - 2, gh - 2, C.Graph2, dashed: true);

        string maj = s.Paused ? "EN PAUSE" : $"MAJ {s.IntervalMs / 1000.0:0.##} S";
        ctx.DrawText(g, gx, 6, maj, GreenFont.Family, 9, C.Grid, shadow: false);
        using (var pc = new Pen(C.Graph, 2f)) g.DrawLine(pc, 366, 12, 384, 12);
        ctx.DrawText(g, 388, 6, "CPU", GreenFont.Family, 9, C.Grid, shadow: false);
        using (var pg = new Pen(C.Graph2, 2f) { DashPattern = [4f, 3f] }) g.DrawLine(pg, 426, 12, 444, 12);
        ctx.DrawText(g, 448, 6, "GPU", GreenFont.Family, 9, C.Grid, shadow: false);

        g.DrawRectangle(gridPen, 10, 272, 220, 9);
        g.DrawRectangle(gridPen, 250, 272, 220, 9);
        using (var bc = new SolidBrush(C.Graph))
            g.FillRectangle(bc, 11, 273, (float)(218.0 * Math.Clamp(s.CpuUsage, 0, 100) / 100.0), 7);
        using (var bg = new SolidBrush(C.Graph2))
            g.FillRectangle(bg, 251, 273, (float)(218.0 * Math.Clamp(s.GpuUsage, 0, 100) / 100.0), 7);

        ctx.DrawText(g, 10, 200, ThemeDrawContext.TempInt(s.CpuTemp), GreenFont.Family, 28, C.Value, budget: 220, sample: "100°C");
        ctx.DrawText(g, 250, 200, ThemeDrawContext.TempInt(s.GpuTemp), GreenFont.Family, 28, C.Value, budget: 220, sample: "100°C");
        ctx.DrawText(g, 10, 248, $"CPU · {s.CpuUsage:0} %", GreenFont.Family, 12, C.Label, budget: 220, sample: "CPU · 100 %");
        ctx.DrawText(g, 250, 248, $"GPU · {s.GpuUsage:0} %", GreenFont.Family, 12, C.Label, budget: 220, sample: "GPU · 100 %");
        ctx.DrawText(g, 10, 290, s.CpuName, GreenFont.Family, 11, C.Grid, budget: 220);
        ctx.DrawText(g, 250, 290, s.GpuName, GreenFont.Family, 11, C.Grid, budget: 220);
    }
}

public sealed class T08Frise : IPanelTheme
{
    public string Key => "08-frise";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        var C = ctx.Colors;
        ctx.DrawGreenBackground(g);
        using var gridPen = new Pen(C.Grid, 1f);

        DrawTrack(g, ctx, 10, s.CpuName, s.CpuTemp, s.CpuUsage, s.HistTempCpu, C.Graph, s.HistorySpanLabel(), gridPen);
        DrawTrack(g, ctx, 170, s.GpuName, s.GpuTemp, s.GpuUsage, s.HistTempGpu, C.Graph2, s.HistorySpanLabel(), gridPen);
    }

    private static void DrawTrack(Graphics g, ThemeDrawContext ctx, int oy, string name, double? temp, double use, IReadOnlyList<double?> hist, Color col, string span, Pen gridPen)
    {
        var C = ctx.Colors;
        int x0 = 158, y = oy + 4, w = 312, h = 114;
        g.DrawRectangle(gridPen, x0, y, w, h);

        int n = Math.Max(1, hist.Count);
        float bw = 310f / n;
        float pad = bw >= 3f ? 1f : 0f;
        float innerH = h - 2f;

        for (int i = 0; i < n; i++)
        {
            double vv = Math.Clamp(hist[i] ?? 50.0, 30.0, 90.0);
            float bh = (float)Math.Min(innerH, Math.Max(6.0, (vv - 30.0) / 60.0 * innerH));
            double op = 0.45 + 0.55 * Math.Clamp((vv - 40.0) / 40.0, 0.0, 1.0);
            float x1 = x0 + 1f + i * bw + pad;
            float rw = Math.Max(1f, bw - 2f * pad);
            using var br = new SolidBrush(Color.FromArgb((int)(op * 255), col));
            g.FillRectangle(br, x1, y + 1f + innerH - bh, rw, bh);
        }

        string shortName = ctx.ShortSuffix(g, name, GreenFont.Family, 10, 138);
        ctx.DrawText(g, 10, oy + 2, shortName, GreenFont.Family, 10, C.Label, budget: 138);
        ctx.DrawText(g, 10, oy + 36, ThemeDrawContext.TempInt(temp), GreenFont.Family, 28, C.Value, budget: 138, sample: "100°C");
        ctx.DrawText(g, 10, oy + 90, $"{use:0} %", GreenFont.Family, 14, col, budget: 138, sample: "100 %");
        ctx.DrawText(g, x0, oy + 122, "−" + span, GreenFont.Family, 8, C.Grid, shadow: false);
        ctx.DrawText(g, x0 + w, oy + 122, "NOW", GreenFont.Family, 8, C.Grid, TextAnchor.NE, shadow: false);
    }
}

public sealed class T09Split : IPanelTheme
{
    public string Key => "09-split";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        var C = ctx.Colors;
        ctx.DrawGreenBackground(g);
        using var framePen = new Pen(C.Frame, 1f);
        using var gridPen = new Pen(C.Grid, 1f);
        g.DrawLine(framePen, 240, 8, 240, 312);

        DrawHalf(g, ctx, 0, s.CpuName, s.CpuTemp, s.CpuUsage, s.HistCpu, C.Graph, gridPen);
        DrawHalf(g, ctx, 240, s.GpuName, s.GpuTemp, s.GpuUsage, s.HistGpu, C.Graph2, gridPen);
    }

    private static void DrawHalf(Graphics g, ThemeDrawContext ctx, int ox, string name, double? temp, double use, IReadOnlyList<double> hist, Color col, Pen gridPen)
    {
        var C = ctx.Colors;
        int sx = ox + 14, sy = 92, sw = 212, sh = 214;
        g.DrawRectangle(gridPen, sx, sy, sw, sh);
        T01AidaPlus.DrawSpark(g, hist, sx + 1, sy + 1, sw - 2, sh - 2, col);
        ctx.DrawText(g, ox + 14, 10, name, GreenFont.Family, 13, C.Label, budget: 212);
        ctx.DrawText(g, ox + 14, 42, ThemeDrawContext.TempInt(temp), GreenFont.Family, 28, C.Value, budget: 115, sample: "100°C");
        ctx.DrawText(g, ox + 226, 46, $"{use:0} %", GreenFont.Family, 22, col, TextAnchor.NE, budget: 90, sample: "100 %");
    }
}
