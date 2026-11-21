namespace CentreControle.Core;

public static class AppPaths
{
    /// <summary>
    /// Retourne le dossier d'installation contenant assets/themes/Moniteur.exe.
    /// </summary>
    public static string ResolveInstallDir()
    {
        var dir = AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        if (Directory.Exists(Path.Combine(dir, "assets")) || Directory.Exists(Path.Combine(dir, "themes")))
            return dir;

        var probe = dir;
        for (int i = 0; i < 10; i++)
        {
            var parent = Directory.GetParent(probe)?.FullName;
            if (parent is null) break;
            if (Directory.Exists(Path.Combine(parent, "assets")))
                return parent;
            probe = parent;
        }
        return dir;
    }

    /// <summary>
    /// En mode portable/dev (dossier inscriptible), stocke config.ini et centre.ini sur place.
    /// Si installe dans Program Files (lecture seule), utilise %ProgramData%\CentreControle\
    /// (partage entre l'utilisateur standard et Moniteur.exe eleve en administrateur).
    /// </summary>
    public static string ResolveDataDir(string installDir)
    {
        if (IsDirectoryWritable(installDir))
            return installDir;

        var sharedDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
            "CentreControle");
        try
        {
            Directory.CreateDirectory(sharedDir);
            var targetCfg = Path.Combine(sharedDir, PanelIpc.PanelConfigName);
            var defaultCfg = Path.Combine(installDir, PanelIpc.PanelConfigName);
            if (!File.Exists(targetCfg) && File.Exists(defaultCfg))
                File.Copy(defaultCfg, targetCfg, overwrite: false);
            return sharedDir;
        }
        catch
        {
            var localDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "CentreControle");
            Directory.CreateDirectory(localDir);
            return localDir;
        }
    }

    private static bool IsDirectoryWritable(string dir)
    {
        try
        {
            var probe = Path.Combine(dir, $".write_test_{Environment.ProcessId}.tmp");
            using (File.Create(probe)) { }
            File.Delete(probe);
            return true;
        }
        catch
        {
            return false;
        }
    }
}
