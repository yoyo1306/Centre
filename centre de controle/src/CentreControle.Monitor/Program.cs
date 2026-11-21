using CentreControle.Core;

namespace CentreControle.Monitor;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        string? themeArg = null;
        int? selftestMs = null;
        string? screenshotPath = null;
        bool setupMode = false;

        foreach (var a in args)
        {
            if (a.StartsWith("--theme=", StringComparison.OrdinalIgnoreCase))
                themeArg = a["--theme=".Length..];
            else if (a.StartsWith("--selftest=", StringComparison.OrdinalIgnoreCase) &&
                     int.TryParse(a["--selftest=".Length..], out int ms))
                selftestMs = ms;
            else if (a.StartsWith("--screenshot=", StringComparison.OrdinalIgnoreCase))
                screenshotPath = a["--screenshot=".Length..];
            else if (a.Equals("--setup", StringComparison.OrdinalIgnoreCase))
                setupMode = true;
            else if (a.Equals("--list", StringComparison.OrdinalIgnoreCase))
            {
                for (int i = 0; i < ThemeCatalog.All.Count; i++)
                    Console.WriteLine($"{i + 1}) {ThemeCatalog.All[i].Key} — {ThemeCatalog.All[i].Name}");
                return 0;
            }
        }

        string baseDir = AppPaths.ResolveInstallDir();

        ApplicationConfiguration.Initialize();
        using var form = new PanelForm(baseDir, themeArg, setupMode, selftestMs, screenshotPath);
        Application.Run(form);
        return 0;
    }
}
