using System.Diagnostics;
using System.Text;

namespace CentreControle.Core;

public static class StartupTask
{
    public const string TaskName = "SensorPanel";

    private static string SchtasksPath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.Windows),
        "System32", "schtasks.exe");

    public static bool IsEnabled()
    {
        try
        {
            using var p = Process.Start(new ProcessStartInfo
            {
                FileName = SchtasksPath,
                Arguments = $"/Query /TN \"{TaskName}\"",
                CreateNoWindow = true,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            });
            if (p is null) return false;
            p.WaitForExit(4000);
            return p.ExitCode == 0;
        }
        catch
        {
            return false;
        }
    }

    public static async Task<(bool Ok, string? Error)> SetEnabledAsync(bool enable, string panelExePath)
    {
        if (enable && !File.Exists(panelExePath))
            return (false, "Moniteur.exe introuvable");
        if (!enable && !IsEnabled())
            return (true, null);

        string args = enable
            ? $"/Create /F /TN \"{TaskName}\" /SC ONLOGON /RL HIGHEST /IT /TR \"\\\"{panelExePath}\\\"\""
            : $"/Delete /F /TN \"{TaskName}\"";

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = SchtasksPath,
                Arguments = args,
                UseShellExecute = true,
                Verb = PanelIpc.IsAdmin() ? "" : "runas",
                WindowStyle = ProcessWindowStyle.Hidden,
            };
            using var proc = Process.Start(psi);
            if (proc is null)
                return (false, "Impossible de lancer schtasks");
            await proc.WaitForExitAsync();
            return IsEnabled() == enable
                ? (true, null)
                : (false, "Modification refusée ou échouée");
        }
        catch (System.ComponentModel.Win32Exception ex) when (ex.NativeErrorCode == 1223)
        {
            return (false, "Action refusée (UAC annulé)");
        }
        catch (Exception ex)
        {
            return (false, ex.Message);
        }
    }
}
