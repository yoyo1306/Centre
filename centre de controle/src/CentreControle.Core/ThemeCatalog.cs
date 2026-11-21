namespace CentreControle.Core;

public sealed record ThemeInfo(string Key, string Name, bool IsGreen)
{
    public string PreviewRelativePath => Path.Combine("themes", Key, "preview.png");
}

public sealed record SpeedOption(string Key, string Label, int IntervalMs);

public static class ThemeCatalog
{
    public const string AppVersion = "2.0.0";
    public const int PanelWidth = 480;
    public const int PanelHeight = 320;
    public const int HistoryWindowMs = 300_000;

    public static readonly IReadOnlyList<SpeedOption> Speeds =
    [
        new("high", "Élevé", 500),
        new("normal", "Normal", 1000),
        new("low", "Faible", 4000),
        new("paused", "En pause", 0),
    ];

    public static readonly int[] BrightnessLevels = [0, 20, 40, 60, 80, 100];

    public static readonly IReadOnlyList<ThemeInfo> All =
    [
        new("01-aida", "Heritage AIDA+", true),
        new("02-hud", "HUD grands chiffres", true),
        new("03-anneaux", "Anneaux (jauges)", true),
        new("04-tuiles", "Tuiles 2x2", true),
        new("05-colonnes", "Colonnes segmentées", true),
        new("06-oscillo", "Oscilloscope", true),
        new("08-frise", "Frise thermique", true),
        new("09-split", "Compact splitscreen", true),
        new("10-modern", "Modern Dark", false),
        new("11-ambre", "Terminal Ambre", false),
        new("12-minimal", "Minimal Mono", false),
        new("13-neon", "Cyber Néon", false),
        new("14-flux", "Flux système", false),
        new("15-atelier", "Atelier", false),
        new("16-thermo", "Thermo", false),
        new("17-heatmap", "Heatmap", false),
        new("18-spectrum", "Spectre", false),
        new("19-aiguilles", "Aiguilles", false),
        new("20-analytics", "Analytics", false),
        new("21-focus", "Focus", false),
    ];

    public static ThemeInfo Resolve(string? key)
    {
        if (string.IsNullOrWhiteSpace(key))
            return All[0];

        var k = key.Trim().ToLowerInvariant();
        foreach (var t in All)
        {
            if (t.Key.Equals(k, StringComparison.OrdinalIgnoreCase))
                return t;
        }

        if (int.TryParse(k, out var num))
        {
            var prefix = $"{num:D2}-";
            foreach (var t in All)
            {
                if (t.Key.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                    return t;
            }
            if (num >= 1 && num <= All.Count)
                return All[num - 1];
        }

        foreach (var t in All)
        {
            if (t.Key.Contains(k, StringComparison.OrdinalIgnoreCase) ||
                t.Name.Contains(k, StringComparison.OrdinalIgnoreCase))
                return t;
        }

        return All[0];
    }

    public static int SpeedIntervalMs(string? speedKey, int fallback = 1000)
    {
        if (string.IsNullOrWhiteSpace(speedKey))
            return fallback;
        var k = speedKey.Trim().ToLowerInvariant();
        foreach (var s in Speeds)
        {
            if (s.Key == k)
                return s.IntervalMs;
        }
        return fallback;
    }
}
