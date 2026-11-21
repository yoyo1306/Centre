using CentreControle.Core;

namespace CentreControle.Monitor.Themes;

public static class ThemeFactory
{
    public static IPanelTheme Create(string? key)
    {
        var resolved = ThemeCatalog.Resolve(key);
        return resolved.Key switch
        {
            "01-aida" => new T01AidaPlus(),
            "02-hud" => new T02Hud(),
            "03-anneaux" => new T03Anneaux(),
            "04-tuiles" => new T04Tuiles(),
            "05-colonnes" => new T05Colonnes(),
            "06-oscillo" => new T06Oscillo(),
            "08-frise" => new T08Frise(),
            "09-split" => new T09Split(),
            "10-modern" => new T10Modern(),
            "11-ambre" => new T11Ambre(),
            "12-minimal" => new T12Minimal(),
            "13-neon" => new T13Neon(),
            "14-flux" => new T14Flux(),
            "15-atelier" => new T15Atelier(),
            "16-thermo" => new T16Thermo(),
            "17-heatmap" => new T17Heatmap(),
            "18-spectrum" => new T18Spectrum(),
            "19-aiguilles" => new T19Aiguilles(),
            "20-analytics" => new T20Analytics(),
            "21-focus" => new T21Focus(),
            _ => new T01AidaPlus(),
        };
    }
}
