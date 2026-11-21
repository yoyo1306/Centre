using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.Globalization;
using System.Runtime.InteropServices;

namespace CentreControle.Monitor;

public enum TextAnchor
{
    NW,
    N,
    NE,
    E,
    Center,
}

public interface IPanelTheme
{
    string Key { get; }
    void Render(Graphics g, ThemeDrawContext ctx, SensorState state);
}

public sealed class ThemeDrawContext : IDisposable
{
    private const uint FR_PRIVATE = 0x10;
    private const uint ANTIALIASED_QUALITY = 4;

    [StructLayout(LayoutKind.Sequential)]
    private struct GDI_SIZE { public int cx, cy; }

    [DllImport("gdi32.dll", CharSet = CharSet.Unicode)]
    private static extern int AddFontResourceExW(string lpszFilename, uint fl, IntPtr pdv);

    [DllImport("gdi32.dll", CharSet = CharSet.Unicode)]
    private static extern bool RemoveFontResourceExW(string lpFileName, uint fl, IntPtr pdv);

    [DllImport("gdi32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr CreateFontW(
        int nHeight, int nWidth, int nEscapement, int nOrientation, int fnWeight,
        uint fdwItalic, uint fdwUnderline, uint fdwStrikeOut, uint fdwCharSet,
        uint fdwOutputPrecision, uint fdwClipPrecision, uint fdwQuality,
        uint fdwPitchAndFamily, string lpszFace);

    [DllImport("gdi32.dll")]
    private static extern IntPtr SelectObject(IntPtr hdc, IntPtr hgdiobj);

    [DllImport("gdi32.dll")]
    private static extern bool DeleteObject(IntPtr ho);

    [DllImport("gdi32.dll")]
    private static extern int SetBkMode(IntPtr hdc, int mode);

    [DllImport("gdi32.dll")]
    private static extern uint SetTextColor(IntPtr hdc, uint color);

    [DllImport("gdi32.dll", CharSet = CharSet.Unicode)]
    private static extern bool TextOutW(IntPtr hdc, int x, int y, string lpString, int c);

    [DllImport("gdi32.dll", CharSet = CharSet.Unicode)]
    private static extern bool GetTextExtentPoint32W(IntPtr hdc, string lpString, int c, out GDI_SIZE psizl);

    private readonly PrivateFontCollection _pfc = new();
    private readonly Dictionary<(string Family, int Px, FontStyle Style), Font> _fontCache = new();
    private readonly Dictionary<int, IntPtr> _gdiDigitalFonts = new();
    private readonly string? _privateFontPath;
    private FontFamily? _digitalFamily;

    public Image? GreenBackground { get; private set; }
    public PaletteColors Colors { get; set; } = new();

    public ThemeDrawContext(string baseDir)
    {
        var fontPath = Path.Combine(baseDir, "assets", "dash-digital.ttf");
        if (File.Exists(fontPath))
        {
            try
            {
                _pfc.AddFontFile(fontPath);
                if (_pfc.Families.Length > 0)
                    _digitalFamily = _pfc.Families[0];
                if (AddFontResourceExW(fontPath, FR_PRIVATE, IntPtr.Zero) > 0)
                    _privateFontPath = fontPath;
            }
            catch { }
        }

        var fondPath = Path.Combine(baseDir, "assets", "Fond.png");
        if (File.Exists(fondPath))
        {
            try
            {
                using var fs = File.OpenRead(fondPath);
                using var raw = Image.FromStream(fs);
                GreenBackground = new Bitmap(raw, 480, 320);
            }
            catch { }
        }
    }

    private IntPtr GetGdiDigitalFont(int px)
    {
        int ipx = Math.Max(6, px);
        if (_gdiDigitalFonts.TryGetValue(ipx, out var hf))
            return hf;
        hf = CreateFontW(-ipx, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, ANTIALIASED_QUALITY, 0, "Dash Digital-7");
        _gdiDigitalFonts[ipx] = hf;
        return hf;
    }

    private static uint ToColorRef(Color c) => (uint)(c.R | (c.G << 8) | (c.B << 16));

    private void DrawGdiDigitalText(Graphics g, float x, float y, string text, float px, Color color,
        TextAnchor anchor, float? budget, string? sample, bool shadow)
    {
        int chosenPx = Math.Max(6, (int)Math.Round(px));
        IntPtr hdc = g.GetHdc();
        try
        {
            SetBkMode(hdc, 1); // TRANSPARENT
            if (budget.HasValue)
            {
                string fitText = sample ?? text;
                while (chosenPx > 7)
                {
                    IntPtr hTest = GetGdiDigitalFont(chosenPx);
                    IntPtr prev = SelectObject(hdc, hTest);
                    GetTextExtentPoint32W(hdc, fitText, fitText.Length, out var szFit);
                    SelectObject(hdc, prev);
                    if (szFit.cx <= budget.Value)
                        break;
                    chosenPx--;
                }
            }

            IntPtr hf = GetGdiDigitalFont(chosenPx);
            IntPtr old = SelectObject(hdc, hf);
            try
            {
                GetTextExtentPoint32W(hdc, text, text.Length, out var sz);
                int dx = anchor switch
                {
                    TextAnchor.N or TextAnchor.Center => (int)Math.Round(x - sz.cx / 2.0),
                    TextAnchor.NE or TextAnchor.E => (int)Math.Round(x - sz.cx),
                    _ => (int)Math.Round(x),
                };
                int dy = anchor switch
                {
                    TextAnchor.E or TextAnchor.Center => (int)Math.Round(y - sz.cy / 2.0),
                    _ => (int)Math.Round(y),
                };

                if (shadow)
                {
                    SetTextColor(hdc, 0x00000000);
                    TextOutW(hdc, dx + 1, dy + 1, text, text.Length);
                }
                SetTextColor(hdc, ToColorRef(color));
                TextOutW(hdc, dx, dy, text, text.Length);
            }
            finally
            {
                SelectObject(hdc, old);
            }
        }
        finally
        {
            g.ReleaseHdc(hdc);
        }
    }

    public Font GetFont(string family, float px, FontStyle style = FontStyle.Regular)
    {
        int ipx = Math.Max(6, (int)Math.Round(px));
        var key = (family, ipx, style);
        if (_fontCache.TryGetValue(key, out var cached))
            return cached;

        Font font;
        if (family.Equals("Dash Digital-7", StringComparison.OrdinalIgnoreCase) && _digitalFamily is not null)
        {
            font = new Font(_digitalFamily, ipx, style, GraphicsUnit.Pixel);
        }
        else
        {
            try { font = new Font(family, ipx, style, GraphicsUnit.Pixel); }
            catch { font = new Font("Consolas", ipx, style, GraphicsUnit.Pixel); }
        }

        _fontCache[key] = font;
        return font;
    }

    public static SizeF Measure(Graphics g, string text, Font font)
    {
        var sz = g.MeasureString(text, font, PointF.Empty, StringFormat.GenericTypographic);
        return new SizeF(sz.Width + 1f, sz.Height);
    }

    public Font FitFont(Graphics g, string family, float startPx, string sample, float maxWidthPx, FontStyle style = FontStyle.Regular)
    {
        float px = startPx;
        while (px > 7f)
        {
            var f = GetFont(family, px, style);
            if (Measure(g, sample, f).Width <= maxWidthPx)
                return f;
            px -= 1f;
        }
        return GetFont(family, 7f, style);
    }

    public void DrawGreenBackground(Graphics g)
    {
        if (GreenBackground is not null)
            g.DrawImage(GreenBackground, 0, 0, 480, 320);
        else
            g.Clear(Colors.Background);
    }

    public void DrawText(Graphics g, float x, float y, string text, string family, float px, Color color,
        TextAnchor anchor = TextAnchor.NW, float? budget = null, string? sample = null, FontStyle style = FontStyle.Regular, bool shadow = true)
    {
        if (family.Equals("Dash Digital-7", StringComparison.OrdinalIgnoreCase))
        {
            DrawGdiDigitalText(g, x, y, text, px, color, anchor, budget, sample, shadow);
            return;
        }

        var font = budget.HasValue
            ? FitFont(g, family, px, sample ?? text, budget.Value, style)
            : GetFont(family, px, style);

        var sz = Measure(g, text, font);
        float dx = anchor switch
        {
            TextAnchor.N or TextAnchor.Center => x - sz.Width / 2f,
            TextAnchor.NE or TextAnchor.E => x - sz.Width,
            _ => x,
        };
        float dy = anchor switch
        {
            TextAnchor.E or TextAnchor.Center => y - sz.Height / 2f,
            _ => y,
        };

        var sf = StringFormat.GenericTypographic;
        if (shadow)
        {
            using var sh = new SolidBrush(Color.Black);
            g.DrawString(text, font, sh, dx + 1f, dy + 1f, sf);
        }
        using var br = new SolidBrush(color);
        g.DrawString(text, font, br, dx, dy, sf);
    }

    public static void DrawCrispRect(Graphics g, Pen pen, int x, int y, int w, int h)
    {
        var prevSmooth = g.SmoothingMode;
        var prevOffset = g.PixelOffsetMode;
        g.SmoothingMode = SmoothingMode.None;
        g.PixelOffsetMode = PixelOffsetMode.Default;
        try
        {
            g.DrawRectangle(pen, x, y, w, h);
        }
        finally
        {
            g.SmoothingMode = prevSmooth;
            g.PixelOffsetMode = prevOffset;
        }
    }

    public void DrawTempGroup(Graphics g, float x, float y, string valueText, string family, float px, Color valColor,
        float unitPx, Color unitColor, float? budget = null)
    {
        var vFont = budget.HasValue
            ? FitFont(g, family, px, "100.0", budget.Value, FontStyle.Regular)
            : GetFont(family, px);
        var uFont = GetFont(family, unitPx);
        var vSz = Measure(g, valueText, vFont);
        float uy = y + vSz.Height * 0.78f - Measure(g, " °C", uFont).Height * 0.78f;
        DrawText(g, x, y, valueText, family, vFont.Size, valColor);
        DrawText(g, x + vSz.Width + 2f, uy, " °C", family, unitPx, unitColor);
    }

    public void DrawTempGroupCentered(Graphics g, float cx, float y, string valueText, string family, float px, Color valColor,
        float unitPx, Color unitColor)
    {
        var vFont = GetFont(family, px);
        var uFont = GetFont(family, unitPx);
        var vSz = Measure(g, valueText, vFont);
        var uSz = Measure(g, " °C", uFont);
        float total = vSz.Width + 2f + uSz.Width;
        float left = cx - total / 2f;
        float uy = y + vSz.Height * 0.78f - uSz.Height * 0.78f;
        DrawText(g, left, y, valueText, family, px, valColor);
        DrawText(g, left + vSz.Width + 2f, uy, " °C", family, unitPx, unitColor);
    }

    public string ShortSuffix(Graphics g, string name, string family, float px, float budget)
    {
        var words = name.ToUpperInvariant().Split(' ', StringSplitOptions.RemoveEmptyEntries);
        if (words.Length == 0) return name.ToUpperInvariant();
        var font = GetFont(family, px);
        string result = words[^1];
        for (int i = words.Length - 2; i >= 0; i--)
        {
            string cand = words[i] + " " + result;
            if (Measure(g, cand, font).Width > budget)
                break;
            result = cand;
        }
        return result;
    }

    public static PointF[] BuildLinePoints(IReadOnlyList<double> hist, float x, float y, float w, float h, double vmax = 100.0)
    {
        int n = hist.Count;
        if (n < 2)
        {
            double v = n == 1 ? hist[0] : 0.0;
            float py = y + h - (float)(Math.Clamp(v, 0.0, vmax) / vmax) * h;
            return [new PointF(x, py), new PointF(x + w, py)];
        }
        var pts = new PointF[n];
        float step = w / (n - 1);
        for (int i = 0; i < n; i++)
        {
            double frac = Math.Clamp(hist[i], 0.0, vmax) / vmax;
            pts[i] = new PointF(x + i * step, y + h - (float)(frac * h));
        }
        return pts;
    }

    public static PointF[] BuildSparkPoints(IReadOnlyList<double> vals, float x, float y, float w, float h, double lo, double hi)
    {
        if (vals.Count == 0) return [];
        IReadOnlyList<double> src = vals.Count == 1 ? [vals[0], vals[0]] : vals;
        int n = src.Count;
        double span = Math.Max(1e-6, hi - lo);
        var pts = new PointF[n];
        for (int i = 0; i < n; i++)
        {
            double p = Math.Clamp((src[i] - lo) / span, 0.0, 1.0);
            float px = x + 3f + i * (w - 6f) / (n - 1f);
            float py = y + 3f + (h - 6f) * (float)(1.0 - p);
            pts[i] = new PointF(px, py);
        }
        return pts;
    }

    public static void DrawSparkArea(Graphics g, PointF[] pts, float bottomY, Color accent, int alpha = 42)
    {
        if (pts.Length < 2) return;
        var poly = new PointF[pts.Length + 2];
        Array.Copy(pts, poly, pts.Length);
        poly[pts.Length] = new PointF(pts[^1].X, bottomY);
        poly[pts.Length + 1] = new PointF(pts[0].X, bottomY);
        using var br = new SolidBrush(Color.FromArgb(alpha, accent));
        g.FillPolygon(br, poly);
    }

    public static PointF Compass(float cx, float cy, float r, double deg)
    {
        double rad = deg * Math.PI / 180.0;
        return new PointF(cx + (float)(r * Math.Sin(rad)), cy - (float)(r * Math.Cos(rad)));
    }

    public static void DrawCompassArc(Graphics g, float cx, float cy, float r, float degStart, float degEnd, Color color, float width)
    {
        float sweep = degEnd - degStart;
        if (Math.Abs(sweep) < 0.1f) return;
        // GDI+ 0 deg = est (3h), sens horaire. Boussole 0 deg = nord (-90 en GDI+).
        using var pen = new Pen(color, width) { StartCap = LineCap.Flat, EndCap = LineCap.Flat };
        g.DrawArc(pen, cx - r, cy - r, r * 2f, r * 2f, degStart - 90f, sweep);
    }

    public static Color Hex(string hex) => ColorTranslator.FromHtml(hex);

    public static Color TempColor(double? t, Color normal, double warm = 65, double hot = 75)
    {
        if (t is null) return normal;
        if (t.Value >= hot) return Hex("#FB7185");
        if (t.Value >= warm) return Hex("#FBBF24");
        return normal;
    }

    private static readonly (double T, int R, int G, int B)[] HeatStops =
    [
        (30, 11, 42, 51), (38, 14, 79, 82), (46, 15, 118, 110),
        (54, 21, 128, 61), (62, 101, 163, 13), (68, 202, 138, 4),
        (74, 234, 88, 12), (80, 220, 38, 38), (100, 127, 29, 29),
    ];

    public static Color HeatColor(double? t)
    {
        if (t is null) return Hex("#14110F");
        double v = Math.Clamp(t.Value, 30.0, 100.0);
        for (int i = 0; i < HeatStops.Length - 1; i++)
        {
            var a = HeatStops[i];
            var b = HeatStops[i + 1];
            if (v <= b.T)
            {
                double f = (v - a.T) / (b.T - a.T);
                return Color.FromArgb(
                    (int)(a.R + (b.R - a.R) * f),
                    (int)(a.G + (b.G - a.G) * f),
                    (int)(a.B + (b.B - a.B) * f));
            }
        }
        return Hex("#7F1D1D");
    }

    public static string TempInt(double? t) => t is null ? "--°C" : $"{t.Value:0}°C";
    public static string TempDec(double? t) => t is null ? "--.- °C" : $"{t.Value.ToString("0.0", CultureInfo.InvariantCulture)} °C";
    public static string TempDecVal(double? t) => t is null ? "--.-" : t.Value.ToString("0.0", CultureInfo.InvariantCulture);

    public static string UptimeStr(double sec)
    {
        long s = (long)Math.Max(0, sec);
        long days = s / 86400;
        long hours = (s % 86400) / 3600;
        long mins = (s % 3600) / 60;
        return days > 0 ? $"{days}j {hours}h" : $"{hours}h {mins:D2}";
    }

    public static string GoStr(double gb)
        => gb >= 10 ? gb.ToString("0", CultureInfo.InvariantCulture) : gb.ToString("0.0", CultureInfo.InvariantCulture);

    public static string RateStr(double mbps)
    {
        if (mbps >= 10) return mbps.ToString("0", CultureInfo.InvariantCulture);
        if (mbps >= 1) return mbps.ToString("0.0", CultureInfo.InvariantCulture);
        return mbps.ToString("0.00", CultureInfo.InvariantCulture);
    }

    public static List<double?> LastN(IReadOnlyList<double?> hist, int n)
    {
        var result = new List<double?>(n);
        int skip = Math.Max(0, hist.Count - n);
        int pad = Math.Max(0, n - hist.Count);
        for (int i = 0; i < pad; i++) result.Add(null);
        for (int i = skip; i < hist.Count; i++) result.Add(hist[i]);
        return result;
    }

    public static List<double?> LastNDoubles(IReadOnlyList<double> hist, int n)
    {
        var result = new List<double?>(n);
        int skip = Math.Max(0, hist.Count - n);
        int pad = Math.Max(0, n - hist.Count);
        for (int i = 0; i < pad; i++) result.Add(null);
        for (int i = skip; i < hist.Count; i++) result.Add(hist[i]);
        return result;
    }

    public void Dispose()
    {
        foreach (var f in _fontCache.Values)
            f.Dispose();
        _fontCache.Clear();
        foreach (var hf in _gdiDigitalFonts.Values)
            if (hf != IntPtr.Zero) DeleteObject(hf);
        _gdiDigitalFonts.Clear();
        if (!string.IsNullOrEmpty(_privateFontPath))
        {
            try { RemoveFontResourceExW(_privateFontPath, FR_PRIVATE, IntPtr.Zero); } catch { }
        }
        GreenBackground?.Dispose();
        _pfc.Dispose();
    }
}
