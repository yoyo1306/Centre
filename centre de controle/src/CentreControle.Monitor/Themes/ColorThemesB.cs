using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Globalization;

namespace CentreControle.Monitor.Themes;

public sealed class T16Thermo : IPanelTheme
{
    public string Key => "16-thermo";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        g.Clear(ThemeDrawContext.Hex("#0B1115"));
        using (var p = new Pen(ThemeDrawContext.Hex("#0E181E"))) g.DrawLine(p, 0, 32, 480, 32);
        ctx.DrawText(g, 16, 9, "THERMO", "Segoe UI", 10, ThemeDrawContext.Hex("#93A4B1"));
        ctx.DrawText(g, 240, 9, "MERCURE · 20–100 °C", "Segoe UI", 8, ThemeDrawContext.Hex("#5F7180"), TextAnchor.N);
        ctx.DrawText(g, 464, 9, DateTime.Now.ToString("HH:mm"), "Segoe UI", 8, ThemeDrawContext.Hex("#5F7180"), TextAnchor.NE);
        using (var p = new Pen(ThemeDrawContext.Hex("#1B2A33"))) g.DrawLine(p, 12, 28, 468, 28);

        DrawOne(g, ctx, 10, "CPU", s.CpuName, s.CpuTemp, s.CpuUsage, s.HistTempCpu, ThemeDrawContext.Hex("#34D399"));
        DrawOne(g, ctx, 246, "GPU", s.GpuName, s.GpuTemp, s.GpuUsage, s.HistTempGpu, ThemeDrawContext.Hex("#38BDF8"));
    }

    private static void DrawOne(Graphics g, ThemeDrawContext ctx, int px, string tag, string name, double? t, double use, IReadOnlyList<double?> hist, Color accent)
    {
        int cx = px + 14, tube = px + 158, inner = tube + 10, bulb = tube + 14;
        using var cardBg = new SolidBrush(ThemeDrawContext.Hex("#0F181E"));
        using var cardBd = new Pen(ThemeDrawContext.Hex("#1E2E38"));
        using var accBr = new SolidBrush(accent);
        g.FillRectangle(cardBg, px, 38, 224, 272);
        g.DrawRectangle(cardBd, px, 38, 224, 272);
        g.FillRectangle(accBr, px, 38, 224, 3);

        ctx.DrawText(g, cx, 51, tag, "Segoe UI", 9, accent);
        ctx.DrawText(g, cx, 65, name, "Segoe UI", 8, ThemeDrawContext.Hex("#7C8B99"), budget: 134);
        ctx.DrawTempGroup(g, cx, 80, ThemeDrawContext.TempDecVal(t), "Segoe UI", 40, ThemeDrawContext.Hex("#E6EDF3"), 13, ThemeDrawContext.Hex("#7C8B99"));
        ctx.DrawText(g, cx, 132, "CHARGE", "Segoe UI", 7, ThemeDrawContext.Hex("#5F7180"));
        ctx.DrawText(g, cx, 142, $"{use:0} %", "Segoe UI", 18, accent);

        using var track = new SolidBrush(ThemeDrawContext.Hex("#1A2730"));
        g.FillRectangle(track, cx, 166, 108, 5);
        g.FillRectangle(accBr, cx, 166, (float)(108.0 * Math.Clamp(use, 0, 100) / 100.0), 5);

        var vals = hist.Where(v => v.HasValue).Select(v => v!.Value).ToList();
        ctx.DrawText(g, cx, 184, "PLAGE", "Segoe UI", 7, ThemeDrawContext.Hex("#5F7180"));
        ctx.DrawText(g, cx, 194, "20–100 °C", "Segoe UI", 8, ThemeDrawContext.Hex("#A7B7C4"));
        ctx.DrawText(g, cx, 212, vals.Count == 0 ? "MIN --" : $"MIN {vals.Min().ToString("0.0", CultureInfo.InvariantCulture)}°", "Segoe UI", 7.5f, ThemeDrawContext.Hex("#5F7180"));
        ctx.DrawText(g, cx, 224, vals.Count == 0 ? "MAX --" : $"MAX {vals.Max().ToString("0.0", CultureInfo.InvariantCulture)}°", "Segoe UI", 7.5f, ThemeDrawContext.Hex("#5F7180"));
        ctx.DrawText(g, cx, 248, "SONDE PACKAGE · MAJ 1 S", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#3F505C"));

        // Tube capsule
        using (var pOuter = new Pen(ThemeDrawContext.Hex("#24333D"), 30f) { StartCap = LineCap.Round, EndCap = LineCap.Round })
            g.DrawLine(pOuter, tube + 14, 72, tube + 14, 250);
        using (var pInner = new Pen(ThemeDrawContext.Hex("#0A0F13"), 26f) { StartCap = LineCap.Round, EndCap = LineCap.Round })
            g.DrawLine(pInner, tube + 14, 72, tube + 14, 250);
        using (var pLine = new Pen(ThemeDrawContext.Hex("#132029"), 1f))
            g.DrawLine(pLine, inner + 1, 72, inner + 1, 250);

        double val = t is null ? 20.0 : Math.Clamp(t.Value, 20.0, 100.0);
        float ly = 250f - (float)((val - 20.0) / 80.0 * 182.0);
        float y65 = 250f - 45f / 80f * 182f;
        float y80 = 250f - 60f / 80f * 182f;

        FillSeg(g, inner, Math.Max(ly, y65), 8f, 256f, accent);
        if (ly < y65) FillSeg(g, inner, Math.Max(ly, y80), 8f, y65, ThemeDrawContext.Hex("#FBBF24"));
        if (ly < y80) FillSeg(g, inner, ly, 8f, y80, ThemeDrawContext.Hex("#FB7185"));

        using (var bOutBg = new SolidBrush(ThemeDrawContext.Hex("#0A0F13")))
        using (var bOutBd = new Pen(ThemeDrawContext.Hex("#24333D"), 1f))
        {
            g.FillEllipse(bOutBg, bulb - 23, 250, 46, 46);
            g.DrawEllipse(bOutBd, bulb - 23, 250, 46, 46);
        }
        using (var bIn = new SolidBrush(ThemeDrawContext.TempColor(t, accent, 65, 80)))
            g.FillEllipse(bIn, bulb - 20, 253, 40, 40);
        using (var men = new Pen(ThemeDrawContext.Hex("#E6EDF3"), 1f))
            g.DrawLine(men, inner - 1, ly, inner + 9, ly);

        for (int v = 20; v <= 100; v += 10)
        {
            float yy = 250f - (v - 20f) / 80f * 182f;
            bool major = v % 20 == 0;
            using var tp = new Pen(ThemeDrawContext.Hex(major ? "#2A3B45" : "#1C2A33"));
            g.DrawLine(tp, tube - (major ? 11 : 5), yy, tube - 2, yy);
            if (major)
                ctx.DrawText(g, tube - 14, yy, v.ToString(), "Segoe UI", 7, ThemeDrawContext.Hex("#5F7180"), TextAnchor.E);
        }
    }

    private static void FillSeg(Graphics g, float x, float y0, float w, float y1, Color c)
    {
        if (y1 <= y0 + 0.2f) return;
        using var br = new SolidBrush(c);
        g.FillRectangle(br, x, y0, w, y1 - y0);
    }
}

public sealed class T17Heatmap : IPanelTheme
{
    public string Key => "17-heatmap";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        g.Clear(ThemeDrawContext.Hex("#0A0908"));
        using (var p = new Pen(ThemeDrawContext.Hex("#14110F"))) g.DrawLine(p, 0, 32, 480, 32);
        ctx.DrawText(g, 16, 9, "HEATMAP", "Segoe UI", 10, ThemeDrawContext.Hex("#FAFAF9"));
        ctx.DrawText(g, 240, 9, "TEMPÉRATURE · 48 SECONDES", "Segoe UI", 7.5f, ThemeDrawContext.Hex("#78716C"), TextAnchor.N);
        ctx.DrawText(g, 464, 9, DateTime.Now.ToString("HH:mm"), "Segoe UI", 8, ThemeDrawContext.Hex("#78716C"), TextAnchor.NE);

        using (var sep = new Pen(ThemeDrawContext.Hex("#221D18")))
        {
            g.DrawLine(sep, 16, 30, 464, 30);
            g.DrawLine(sep, 240, 42, 240, 130);
            g.DrawLine(sep, 16, 292, 464, 292);
        }

        DrawCard(g, ctx, 16, "CPU", s.CpuName, s.CpuTemp, "PACKAGE · ACTUEL", ThemeDrawContext.Hex("#FB923C"));
        DrawCard(g, ctx, 248, "GPU", s.GpuName, s.GpuTemp, "CORE · ACTUEL", ThemeDrawContext.Hex("#60A5FA"));

        ctx.DrawText(g, 58, 142, "-48 S", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#57534E"));
        ctx.DrawText(g, 261, 142, "-24 S", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#57534E"), TextAnchor.N);
        ctx.DrawText(g, 464, 142, "MAINT.", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#57534E"), TextAnchor.NE);

        ctx.DrawText(g, 16, 158, "CPU", "Segoe UI", 7.5f, ThemeDrawContext.Hex("#FB923C"));
        ctx.DrawText(g, 16, 170, s.CpuTemp is null ? "--.-°" : $"{ThemeDrawContext.TempDecVal(s.CpuTemp)}°", "Segoe UI", 7, ThemeDrawContext.Hex("#A8A29E"));
        ctx.DrawText(g, 16, 200, "GPU", "Segoe UI", 7.5f, ThemeDrawContext.Hex("#60A5FA"));
        ctx.DrawText(g, 16, 212, s.GpuTemp is null ? "--.-°" : $"{ThemeDrawContext.TempDecVal(s.GpuTemp)}°", "Segoe UI", 7, ThemeDrawContext.Hex("#A8A29E"));

        DrawStrip(g, 156, ThemeDrawContext.LastN(s.HistTempCpu, 48));
        DrawStrip(g, 198, ThemeDrawContext.LastN(s.HistTempGpu, 48));

        ctx.DrawText(g, 16, 246, "TEMPÉRATURE", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#57534E"));
        for (int i = 0; i < 12; i++)
        {
            using var br = new SolidBrush(ThemeDrawContext.HeatColor(30.0 + i * 70.0 / 11.0));
            g.FillRectangle(br, 16f + i * 19.5f, 258, 19.8f, 8);
        }
        ctx.DrawText(g, 16, 270, "30", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#78716C"));
        ctx.DrawText(g, 100, 270, "55", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#78716C"), TextAnchor.N);
        ctx.DrawText(g, 183, 270, "80", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#78716C"), TextAnchor.N);
        ctx.DrawText(g, 250, 270, "100", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#78716C"), TextAnchor.NE);

        ctx.DrawText(g, 464, 246, "CELLULE = 1 S", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#57534E"), TextAnchor.NE);
        ctx.DrawText(g, 464, 258, "SEUILS 65° / 80°", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#A8A29E"), TextAnchor.NE);
        ctx.DrawText(g, 464, 270, "48 POINTS", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#57534E"), TextAnchor.NE);
        ctx.DrawText(g, 16, 300, "RAFRAÎCHISSEMENT 1 HZ · HISTORIQUE 48 S", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#57534E"));
        ctx.DrawText(g, 464, 300, "SOURCE LHM / NVML", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#57534E"), TextAnchor.NE);
    }

    private static void DrawCard(Graphics g, ThemeDrawContext ctx, int px, string label, string name, double? t, string sub, Color accent)
    {
        ctx.DrawText(g, px, 40, label, "Segoe UI", 8, accent);
        ctx.DrawText(g, px, 52, name, "Segoe UI", 7, ThemeDrawContext.Hex("#78716C"), budget: 214);
        ctx.DrawTempGroup(g, px, 62, ThemeDrawContext.TempDecVal(t), "Segoe UI", 40, ThemeDrawContext.Hex("#FAFAF9"), 13, ThemeDrawContext.Hex("#78716C"), budget: 222);
        ctx.DrawText(g, px, 114, sub, "Segoe UI", 6.5f, ThemeDrawContext.Hex("#57534E"));
    }

    private static void DrawStrip(Graphics g, int y0, List<double?> vals)
    {
        float step = (464f - 58f) / 48f;
        for (int i = 0; i < 48; i++)
        {
            float xa = 58f + i * step + 0.5f;
            float w = step - 1f;
            using var br = new SolidBrush(ThemeDrawContext.HeatColor(vals[i]));
            g.FillRectangle(br, xa, y0, w, 34f);
            if (i == 47)
            {
                using var bd = new Pen(ThemeDrawContext.Hex("#FAFAF9"), 1f);
                g.DrawRectangle(bd, xa, y0, w, 34f);
            }
        }
    }
}

public sealed class T18Spectrum : IPanelTheme
{
    public string Key => "18-spectrum";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        g.Clear(ThemeDrawContext.Hex("#060A14"));
        using (var p = new Pen(ThemeDrawContext.Hex("#101A2E"))) g.DrawLine(p, 16, 30, 464, 30);
        using (var p = new Pen(ThemeDrawContext.Hex("#0E1830"))) g.DrawLine(p, 151, 38, 151, 304);
        using (var p = new Pen(ThemeDrawContext.Hex("#0F1B2D"))) g.DrawLine(p, 16, 180, 144, 180);

        ctx.DrawText(g, 16, 9, "SPECTRE", "Segoe UI", 10, ThemeDrawContext.Hex("#22D3EE"));
        ctx.DrawText(g, 240, 9, "48 S · HAUTEUR = CHARGE · COULEUR = TEMP.", "Segoe UI", 7, ThemeDrawContext.Hex("#52627A"), TextAnchor.N);
        ctx.DrawText(g, 464, 9, DateTime.Now.ToString("HH:mm"), "Segoe UI", 8, ThemeDrawContext.Hex("#52627A"), TextAnchor.NE);

        // CPU side
        ctx.DrawText(g, 16, 44, "CPU", "Segoe UI", 9, ThemeDrawContext.Hex("#22D3EE"));
        ctx.DrawText(g, 16, 56, s.CpuName, "Segoe UI", 7, ThemeDrawContext.Hex("#52627A"), budget: 128);
        ctx.DrawTempGroup(g, 16, 68, ThemeDrawContext.TempDecVal(s.CpuTemp), "Segoe UI", 32,
            ThemeDrawContext.TempColor(s.CpuTemp, ThemeDrawContext.Hex("#34D399"), 65, 80), 13, ThemeDrawContext.Hex("#52627A"), budget: 132);
        ctx.DrawText(g, 16, 110, "CHARGE", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#3F5068"));
        ctx.DrawText(g, 16, 120, $"{s.CpuUsage:0} %", "Segoe UI", 18, ThemeDrawContext.Hex("#22D3EE"));
        DrawBar(g, 16, 148, 128, 5, s.CpuUsage, ThemeDrawContext.Hex("#22D3EE"));
        ctx.DrawText(g, 16, 158, s.CpuFreqMhz <= 0 ? "PACKAGE · --" : $"PACKAGE · {(s.CpuFreqMhz / 1000.0).ToString("0.0", CultureInfo.InvariantCulture)} GHz",
            "Segoe UI", 6.5f, ThemeDrawContext.Hex("#3F5068"), budget: 132);

        // GPU side
        ctx.DrawText(g, 16, 190, "GPU", "Segoe UI", 9, ThemeDrawContext.Hex("#818CF8"));
        ctx.DrawText(g, 16, 202, s.GpuName, "Segoe UI", 7, ThemeDrawContext.Hex("#52627A"), budget: 128);
        ctx.DrawTempGroup(g, 16, 214, ThemeDrawContext.TempDecVal(s.GpuTemp), "Segoe UI", 32,
            ThemeDrawContext.TempColor(s.GpuTemp, ThemeDrawContext.Hex("#818CF8"), 65, 80), 13, ThemeDrawContext.Hex("#52627A"), budget: 132);
        ctx.DrawText(g, 16, 258, "CHARGE", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#3F5068"));
        ctx.DrawText(g, 16, 268, $"{s.GpuUsage:0} %", "Segoe UI", 18, ThemeDrawContext.Hex("#818CF8"));
        DrawBar(g, 16, 294, 128, 5, s.GpuUsage, ThemeDrawContext.Hex("#818CF8"));
        ctx.DrawText(g, 16, 304, s.GpuPowerW is null ? "CORE · --" : $"CORE · {s.GpuPowerW.Value:0} W",
            "Segoe UI", 6.5f, ThemeDrawContext.Hex("#3F5068"), budget: 132);

        foreach (var (yy, col) in new[] { (52, "#0C1626"), (108, "#0C1626"), (136, "#0A1220"), (204, "#0A1220"), (244, "#0C1626") })
        {
            using var gp = new Pen(ThemeDrawContext.Hex(col));
            g.DrawLine(gp, 160, yy, 464, yy);
        }
        using (var mid = new Pen(ThemeDrawContext.Hex("#1E293B"))) g.DrawLine(mid, 160, 164, 464, 164);

        DrawBars(g, ThemeDrawContext.LastNDoubles(s.HistCpu, 48), ThemeDrawContext.LastN(s.HistTempCpu, 48), 164f, true, ThemeDrawContext.Hex("#22D3EE"), 112f);
        DrawBars(g, ThemeDrawContext.LastNDoubles(s.HistGpu, 48), ThemeDrawContext.LastN(s.HistTempGpu, 48), 165f, false, ThemeDrawContext.Hex("#818CF8"), 80f);

        ctx.DrawText(g, 464, 42, "CPU ↑", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#22D3EE"), TextAnchor.NE);
        ctx.DrawText(g, 464, 278, "GPU ↓", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#818CF8"), TextAnchor.NE);
        ctx.DrawText(g, 160, 304, "-48 S", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#334155"));
        ctx.DrawText(g, 464, 304, "MAINT.", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#334155"), TextAnchor.NE);
    }

    private static void DrawBar(Graphics g, int x, int y, int w, int h, double pct, Color c)
    {
        using var bg = new SolidBrush(ThemeDrawContext.Hex("#0F1B2D"));
        using var fg = new SolidBrush(c);
        g.FillRectangle(bg, x, y, w, h);
        g.FillRectangle(fg, x, y, (float)(w * Math.Clamp(pct, 0, 100) / 100.0), h);
    }

    private static void DrawBars(Graphics g, List<double?> uses, List<double?> temps, float baseY, bool up, Color baseCol, float scale)
    {
        float step = 304f / 48f;
        float colw = step - 1.1f;
        using var hiBr = new SolidBrush(Color.FromArgb(140, Color.White));
        for (int i = 0; i < 48; i++)
        {
            if (uses[i] is null || uses[i]!.Value <= 0.01) continue;
            float x = 160f + i * step;
            float bh = (float)Math.Max(1.0, Math.Clamp(uses[i]!.Value, 0, 100) / 100.0 * scale);
            using var br = new SolidBrush(ThemeDrawContext.TempColor(temps[i], baseCol, 65, 80));
            if (up)
            {
                g.FillRectangle(br, x, baseY - bh, colw, bh);
                g.FillRectangle(hiBr, x, baseY - bh - 1f, colw, 1f);
            }
            else
            {
                g.FillRectangle(br, x, baseY, colw, bh);
                g.FillRectangle(hiBr, x, baseY + bh, colw, 1f);
            }
        }
    }
}

public sealed class T19Aiguilles : IPanelTheme
{
    public string Key => "19-aiguilles";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        g.Clear(ThemeDrawContext.Hex("#100D0A"));
        using (var p = new Pen(ThemeDrawContext.Hex("#2A211B"))) g.DrawLine(p, 16, 28, 464, 28);
        using (var p = new Pen(ThemeDrawContext.Hex("#1A1512"))) g.DrawLine(p, 240, 34, 240, 306);

        ctx.DrawText(g, 16, 9, "AIGUILLES", "Segoe UI", 10, ThemeDrawContext.Hex("#F59E0B"));
        ctx.DrawText(g, 240, 9, "TEMPÉRATURE · 20–100 °C", "Segoe UI", 7.5f, ThemeDrawContext.Hex("#8A7A68"), TextAnchor.N);
        ctx.DrawText(g, 464, 9, DateTime.Now.ToString("HH:mm"), "Segoe UI", 8, ThemeDrawContext.Hex("#8A7A68"), TextAnchor.NE);

        DrawGauge(g, ctx, 120, "CPU", s.CpuName, s.CpuTemp, s.CpuUsage);
        DrawGauge(g, ctx, 360, "GPU", s.GpuName, s.GpuTemp, s.GpuUsage);
    }

    private static void DrawGauge(Graphics g, ThemeDrawContext ctx, float cx, string label, string name, double? t, double use)
    {
        float cy = 160f, r = 84f;
        ThemeDrawContext.DrawCompassArc(g, cx, cy, r, -120, 120, ThemeDrawContext.Hex("#2A211B"), 5f);
        ThemeDrawContext.DrawCompassArc(g, cx, cy, r, -120, 15, ThemeDrawContext.Hex("#2E8B6B"), 5f);
        ThemeDrawContext.DrawCompassArc(g, cx, cy, r, 15, 60, ThemeDrawContext.Hex("#A56A1C"), 5f);
        ThemeDrawContext.DrawCompassArc(g, cx, cy, r, 60, 120, ThemeDrawContext.Hex("#A03A3A"), 5f);

        using (var tp = new Pen(ThemeDrawContext.Hex("#5B4A3A")))
        {
            for (int v = 20; v <= 100; v += 10)
            {
                double ang = -120.0 + (v - 20.0) / 80.0 * 240.0;
                g.DrawLine(tp, ThemeDrawContext.Compass(cx, cy, 90, ang), ThemeDrawContext.Compass(cx, cy, 95, ang));
                if (v % 20 == 0)
                {
                    var pt = ThemeDrawContext.Compass(cx, cy, 103, ang);
                    ctx.DrawText(g, pt.X, pt.Y, v.ToString(), "Segoe UI", 6.5f, ThemeDrawContext.Hex("#8A7A68"), TextAnchor.Center);
                }
            }
        }

        double val = t is null ? 20.0 : Math.Clamp(t.Value, 20.0, 100.0);
        double needleAng = -120.0 + (val - 20.0) / 80.0 * 240.0;
        var n0 = ThemeDrawContext.Compass(cx, cy, -14, needleAng);
        var n1 = ThemeDrawContext.Compass(cx, cy, 61, needleAng);
        using (var np = new Pen(ThemeDrawContext.Hex("#F97316"), 3f) { StartCap = LineCap.Round, EndCap = LineCap.Round })
            g.DrawLine(np, n0, n1);

        using (var hb = new SolidBrush(ThemeDrawContext.Hex("#100D0A")))
        using (var hp = new Pen(ThemeDrawContext.Hex("#F97316"), 2f))
        {
            g.FillEllipse(hb, cx - 8, cy - 8, 16, 16);
            g.DrawEllipse(hp, cx - 8, cy - 8, 16, 16);
        }
        using (var cb = new SolidBrush(ThemeDrawContext.Hex("#F5F0E8")))
            g.FillEllipse(cb, cx - 2, cy - 2, 4, 4);

        ctx.DrawText(g, cx, 30, label, "Segoe UI", 9, ThemeDrawContext.Hex("#F59E0B"), TextAnchor.N);
        ctx.DrawText(g, cx, 42, name, "Segoe UI", 7.5f, ThemeDrawContext.Hex("#8A7A68"), TextAnchor.N, budget: 215);
        ctx.DrawTempGroupCentered(g, cx, 232, ThemeDrawContext.TempDecVal(t), "Segoe UI", 26, ThemeDrawContext.Hex("#F5F0E8"), 12, ThemeDrawContext.Hex("#8A7A68"));
        ctx.DrawText(g, cx, 270, "CHARGE", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#8A7A68"), TextAnchor.N);
        ctx.DrawText(g, cx, 280, $"{use:0} %", "Segoe UI", 14, ThemeDrawContext.Hex("#F59E0B"), TextAnchor.N);

        using var bg = new SolidBrush(ThemeDrawContext.Hex("#2A211B"));
        using var fg = new SolidBrush(ThemeDrawContext.Hex("#F59E0B"));
        g.FillRectangle(bg, cx - 60, 300, 120, 4);
        g.FillRectangle(fg, cx - 60, 300, (float)(120.0 * Math.Clamp(use, 0, 100) / 100.0), 4);
    }
}

public sealed class T20Analytics : IPanelTheme
{
    public string Key => "20-analytics";

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        g.Clear(ThemeDrawContext.Hex("#0B0F14"));
        using (var p = new Pen(ThemeDrawContext.Hex("#1E293B")))
        {
            g.DrawLine(p, 16, 30, 464, 30);
            g.DrawLine(p, 16, 306, 464, 306);
        }

        ctx.DrawText(g, 16, 9, "ANALYTICS", "Segoe UI", 10, ThemeDrawContext.Hex("#38BDF8"));
        ctx.DrawText(g, 240, 9, $"FENÊTRE {s.HistorySpanLabel()} · {s.HistoryCapacity} POINTS", "Segoe UI", 7.5f, ThemeDrawContext.Hex("#64748B"), TextAnchor.N);
        ctx.DrawText(g, 464, 9, DateTime.Now.ToString("HH:mm"), "Segoe UI", 8, ThemeDrawContext.Hex("#64748B"), TextAnchor.NE);

        string cpuDet = s.CpuFreqMhz <= 0 ? "--" : $"{(s.CpuFreqMhz / 1000.0).ToString("0.0", CultureInfo.InvariantCulture)} GHz";
        string gpuDet = s.GpuPowerW is null ? "--" : $"{s.GpuPowerW.Value:0} W";
        DrawCard(g, ctx, 36, "CPU", s.CpuName, s.CpuUsage, s.HistTempCpu, cpuDet, ThemeDrawContext.Hex("#38BDF8"));
        DrawCard(g, ctx, 174, "GPU", s.GpuName, s.GpuUsage, s.HistTempGpu, gpuDet, ThemeDrawContext.Hex("#A78BFA"));

        ctx.DrawText(g, 16, 310, "ÉCHANTILLON 1 S · MOYENNE / PIC CALCULÉES SUR L’HISTORIQUE", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#52627A"));
        ctx.DrawText(g, 464, 310, "SEUILS 65° / 80°", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#52627A"), TextAnchor.NE);
    }

    private static void DrawCard(Graphics g, ThemeDrawContext ctx, int y, string label, string name, double use, IReadOnlyList<double?> hist, string detail, Color accent)
    {
        using var bg = new SolidBrush(ThemeDrawContext.Hex("#111821"));
        using var bd = new Pen(ThemeDrawContext.Hex("#243244"));
        using var ab = new SolidBrush(accent);
        g.FillRectangle(bg, 10, y, 460, 130);
        g.DrawRectangle(bd, 10, y, 460, 130);
        g.FillRectangle(ab, 10, y, 3, 130);

        ctx.DrawText(g, 18, y + 8, label, "Segoe UI", 9, accent);
        ctx.DrawText(g, 46, y + 8, name, "Segoe UI", 8, ThemeDrawContext.Hex("#7C8B99"), budget: 200);
        ctx.DrawText(g, 456, y + 8, "5 MIN", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#5F7180"), TextAnchor.NE);

        var vals = hist.Where(v => v.HasValue).Select(v => v!.Value).ToList();
        using (var sbg = new SolidBrush(ThemeDrawContext.Hex("#0A1119")))
            g.FillRectangle(sbg, 262, y + 22, 194, 62);

        if (vals.Count > 0)
        {
            double last = vals[^1], mean = vals.Average(), peak = vals.Max();
            double delta = last - mean;
            ctx.DrawTempGroup(g, 18, y + 22, last.ToString("0.0", CultureInfo.InvariantCulture), "Segoe UI", 36, ThemeDrawContext.Hex("#E6EDF3"), 14, ThemeDrawContext.Hex("#7C8B99"), budget: 225);
            ctx.DrawText(g, 132, y + 48, "MOYENNE", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#5F7180"));
            ctx.DrawText(g, 132, y + 58, $"{mean.ToString("0.0", CultureInfo.InvariantCulture)}°", "Segoe UI", 14, ThemeDrawContext.Hex("#E6EDF3"));
            ctx.DrawText(g, 198, y + 48, "PIC", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#5F7180"));
            ctx.DrawText(g, 198, y + 58, $"{peak.ToString("0.0", CultureInfo.InvariantCulture)}°", "Segoe UI", 14, ThemeDrawContext.Hex("#FBBF24"));
            ctx.DrawText(g, 18, y + 78, $"TENDANCE {(delta >= 0 ? "+" : "")}{delta.ToString("0.0", CultureInfo.InvariantCulture)}° VS MOY",
                "Segoe UI", 7.5f, ThemeDrawContext.Hex(delta > 0 ? "#FBBF24" : "#34D399"), budget: 226);

            double lo = vals.Min(), hi = vals.Max();
            if (hi - lo < 6.0) { double m = (lo + hi) / 2.0; lo = m - 3.0; hi = m + 3.0; }
            else { lo -= 1.0; hi += 1.0; }

            var pts = ThemeDrawContext.BuildSparkPoints(vals, 264, y + 24, 190, 58, lo, hi);
            ThemeDrawContext.DrawSparkArea(g, pts, y + 82, accent, 32);
            double p = Math.Clamp((mean - lo) / Math.Max(1e-6, hi - lo), 0, 1);
            float ay = y + 27f + 52f * (float)(1.0 - p);
            using (var ap = new Pen(accent, 1f) { DashPattern = [3f, 3f] })
                g.DrawLine(ap, 267, ay, 451, ay);
            if (pts.Length >= 2)
            {
                using var lp = new Pen(accent, 2f) { LineJoin = LineJoin.Round };
                g.DrawLines(lp, pts);
                var d = pts[^1];
                using var dp = new Pen(ThemeDrawContext.Hex("#0B0F14"), 1f);
                g.FillEllipse(ab, d.X - 2.6f, d.Y - 2.6f, 5.2f, 5.2f);
                g.DrawEllipse(dp, d.X - 2.6f, d.Y - 2.6f, 5.2f, 5.2f);
            }
        }
        else
        {
            ctx.DrawTempGroup(g, 18, y + 22, "--.-", "Segoe UI", 36, ThemeDrawContext.Hex("#E6EDF3"), 14, ThemeDrawContext.Hex("#7C8B99"), budget: 225);
        }

        ctx.DrawText(g, 18, y + 92, $"CHARGE {use:0} % · {detail}", "Segoe UI", 7.5f, ThemeDrawContext.Hex("#7C8B99"), budget: 226);
        using var track = new SolidBrush(ThemeDrawContext.Hex("#1C2630"));
        g.FillRectangle(track, 18, y + 112, 438, 4);
        g.FillRectangle(ab, 18, y + 112, (float)(438.0 * Math.Clamp(use, 0, 100) / 100.0), 4);
    }
}

public sealed class T21Focus : IPanelTheme
{
    public string Key => "21-focus";

    private readonly Stopwatch _sw = Stopwatch.StartNew();
    private bool _gpuFocus;

    public void Render(Graphics g, ThemeDrawContext ctx, SensorState s)
    {
        double elapsed = _sw.Elapsed.TotalSeconds;
        int flips = (int)(elapsed / 10.0);
        if (flips > 0)
        {
            if (flips % 2 == 1) _gpuFocus = !_gpuFocus;
            _sw.Restart();
            elapsed %= 10.0;
        }
        int rem = Math.Clamp(10 - (int)elapsed, 1, 10);

        g.Clear(ThemeDrawContext.Hex("#07090D"));
        using (var gp = new Pen(ThemeDrawContext.Hex("#0A0F16")))
        {
            foreach (int x in new[] { 60, 180, 300, 420 }) g.DrawLine(gp, x, 0, x, 320);
            foreach (int y in new[] { 80, 160, 240 }) g.DrawLine(gp, 0, y, 480, y);
        }
        using (var sp = new Pen(ThemeDrawContext.Hex("#16202A"))) g.DrawLine(sp, 16, 28, 464, 28);
        using (var vp = new Pen(ThemeDrawContext.Hex("#131C26"))) g.DrawLine(vp, 318, 36, 318, 226);

        ctx.DrawText(g, 16, 9, "FOCUS", "Segoe UI", 10, ThemeDrawContext.Hex("#4ADE80"));
        ctx.DrawText(g, 240, 9, "BASCULE AUTOMATIQUE · 10 S", "Segoe UI", 7, ThemeDrawContext.Hex("#5B6675"), TextAnchor.N);
        ctx.DrawText(g, 464, 9, DateTime.Now.ToString("HH:mm"), "Segoe UI", 8, ThemeDrawContext.Hex("#5B6675"), TextAnchor.NE);

        string label = _gpuFocus ? "GPU" : "CPU";
        string tag = _gpuFocus ? "CORE" : "PACKAGE";
        Color accent = ThemeDrawContext.Hex(_gpuFocus ? "#A78BFA" : "#4ADE80");
        string name = _gpuFocus ? s.GpuName : s.CpuName;
        double? t = _gpuFocus ? s.GpuTemp : s.CpuTemp;
        double use = _gpuFocus ? s.GpuUsage : s.CpuUsage;
        var hist = _gpuFocus ? s.HistTempGpu : s.HistTempCpu;
        string freq = _gpuFocus || s.CpuFreqMhz <= 0 ? "--" : $"{(s.CpuFreqMhz / 1000.0).ToString("0.0", CultureInfo.InvariantCulture)} GHz";
        string power = !_gpuFocus || s.GpuPowerW is null ? "--" : $"{s.GpuPowerW.Value:0} W";
        string source = _gpuFocus ? "NVML" : "LHM";

        ctx.DrawText(g, 16, 40, label, "Segoe UI", 10, accent);
        ctx.DrawText(g, 52, 41, tag, "Segoe UI", 6.5f, ThemeDrawContext.Hex("#5B6675"));
        ctx.DrawText(g, 16, 54, name, "Segoe UI", 8, ThemeDrawContext.Hex("#8A94A6"), budget: 270);
        ctx.DrawTempGroup(g, 16, 62, ThemeDrawContext.TempDecVal(t), "Segoe UI", 64, ThemeDrawContext.Hex("#E6EDF3"), 20, ThemeDrawContext.Hex("#7C8B99"), budget: 290);

        ctx.DrawText(g, 16, 154, "CHARGE", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#5B6675"));
        ctx.DrawText(g, 16, 164, $"{use:0} %", "Segoe UI", 20, accent);
        ctx.DrawText(g, 100, 154, "FRÉQUENCE", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#5B6675"));
        ctx.DrawText(g, 100, 164, freq, "Segoe UI", 13, ThemeDrawContext.Hex("#E6EDF3"), budget: 78);
        ctx.DrawText(g, 184, 154, "PUISSANCE", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#5B6675"));
        ctx.DrawText(g, 184, 164, power, "Segoe UI", 13, ThemeDrawContext.Hex("#E6EDF3"), budget: 68);
        var vals = hist.Where(v => v.HasValue).Select(v => v!.Value).ToList();
        ctx.DrawText(g, 256, 154, "MOYENNE", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#5B6675"));
        ctx.DrawText(g, 256, 164, vals.Count == 0 ? "--.-°" : $"{vals.Average().ToString("0.0", CultureInfo.InvariantCulture)}°", "Segoe UI", 13, ThemeDrawContext.Hex("#E6EDF3"), budget: 64);

        using (var bg = new SolidBrush(ThemeDrawContext.Hex("#16202A")))
        using (var fg = new SolidBrush(accent))
        {
            g.FillRectangle(bg, 16, 200, 288, 6);
            g.FillRectangle(fg, 16, 200, (float)(288.0 * Math.Clamp(use, 0, 100) / 100.0), 6);
        }
        ctx.DrawText(g, 16, 214, $"DERNIER RELEVÉ {DateTime.Now:HH:mm:ss} · {source}", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#3F4B59"));

        // Countdown ring
        ctx.DrawText(g, 398, 44, "BASCULE VERS", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#5B6675"), TextAnchor.N);
        ctx.DrawText(g, 398, 54, _gpuFocus ? "CPU" : "GPU", "Segoe UI", 9, ThemeDrawContext.Hex(_gpuFocus ? "#4ADE80" : "#A78BFA"), TextAnchor.N);
        using (var op = new Pen(ThemeDrawContext.Hex("#1C2630"), 1f))
            g.DrawEllipse(op, 344, 76, 108, 108);
        for (int i = 0; i < 10; i++)
        {
            var col = ThemeDrawContext.Hex(i < rem ? "#F59E0B" : "#1C2630");
            ThemeDrawContext.DrawCompassArc(g, 398, 130, 54, i * 36 + 4, i * 36 + 32, col, 6f);
        }
        ctx.DrawText(g, 398, 108, rem.ToString(), "Segoe UI", 32, ThemeDrawContext.Hex("#F5F5F4"), TextAnchor.N);
        ctx.DrawText(g, 398, 150, "SECONDES", "Segoe UI", 6, ThemeDrawContext.Hex("#5B6675"), TextAnchor.N);
        ctx.DrawText(g, 398, 192, "CYCLE 10 S", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#5B6675"), TextAnchor.N);

        // Bottom secondary banner
        string oLabel = _gpuFocus ? "CPU" : "GPU";
        Color oAccent = ThemeDrawContext.Hex(_gpuFocus ? "#4ADE80" : "#A78BFA");
        string oName = _gpuFocus ? s.CpuName : s.GpuName;
        double? ot = _gpuFocus ? s.CpuTemp : s.GpuTemp;
        double oUse = _gpuFocus ? s.CpuUsage : s.GpuUsage;
        var oHist = _gpuFocus ? s.HistTempCpu : s.HistTempGpu;

        using (var bbg = new SolidBrush(ThemeDrawContext.Hex("#0D1219")))
        using (var bbd = new Pen(ThemeDrawContext.Hex("#1B2634")))
        using (var btop = new SolidBrush(oAccent))
        {
            g.FillRectangle(bbg, 16, 236, 448, 68);
            g.DrawRectangle(bbd, 16, 236, 448, 68);
            g.FillRectangle(btop, 16, 236, 448, 2);
        }
        ctx.DrawText(g, 28, 246, oLabel, "Segoe UI", 8, oAccent);
        ctx.DrawText(g, 28, 258, oName, "Segoe UI", 7, ThemeDrawContext.Hex("#5B6675"), budget: 200);
        ctx.DrawText(g, 28, 270, ThemeDrawContext.TempDec(ot), "Segoe UI", 19, ThemeDrawContext.Hex("#E6EDF3"), budget: 80);
        ctx.DrawText(g, 112, 268, "CHARGE", "Segoe UI", 6.5f, ThemeDrawContext.Hex("#5B6675"));
        ctx.DrawText(g, 112, 278, $"{oUse:0} %", "Segoe UI", 15, oAccent, budget: 58);

        var bvals = oHist.Where(v => v.HasValue).Select(v => v!.Value).TakeLast(48).ToList();
        if (bvals.Count > 0)
        {
            double lo = bvals.Min(), hi = bvals.Max();
            if (hi - lo < 4.0) { double m = (lo + hi) / 2.0; lo = m - 2.0; hi = m + 2.0; }
            else { lo -= 1.0; hi += 1.0; }
            var pts = ThemeDrawContext.BuildSparkPoints(bvals, 240, 250, 208, 36, lo, hi);
            ThemeDrawContext.DrawSparkArea(g, pts, 286, oAccent, 32);
            if (pts.Length >= 2)
            {
                using var lp = new Pen(oAccent, 2f) { LineJoin = LineJoin.Round };
                g.DrawLines(lp, pts);
                var d = pts[^1];
                using var db = new SolidBrush(oAccent);
                using var dp = new Pen(ThemeDrawContext.Hex("#0D1219"), 1f);
                g.FillEllipse(db, d.X - 2.6f, d.Y - 2.6f, 5.2f, 5.2f);
                g.DrawEllipse(dp, d.X - 2.6f, d.Y - 2.6f, 5.2f, 5.2f);
            }
        }
        ctx.DrawText(g, 448, 292, "-48 S", "Segoe UI", 6, ThemeDrawContext.Hex("#3F4B59"), TextAnchor.NE);
    }
}
