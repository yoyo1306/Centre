using System.Diagnostics;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;

namespace CentreControle.Core;

public static class PanelIpc
{
    public const string PipeName = "CentreControlePanelPipe";
    public const string PanelExeName = "Moniteur.exe";
    public const string PanelConfigName = "config.ini";

    public static bool IsAdmin()
    {
        try
        {
            using var id = WindowsIdentity.GetCurrent();
            return new WindowsPrincipal(id).IsInRole(WindowsBuiltInRole.Administrator);
        }
        catch
        {
            return false;
        }
    }

    public static bool IsPanelRunning()
    {
        try
        {
            return Process.GetProcessesByName("Moniteur").Length > 0;
        }
        catch
        {
            return false;
        }
    }

    private static bool TrySendPipe(string payload)
    {
        try
        {
            using var client = new NamedPipeClientStream(".", PipeName, PipeDirection.Out);
            client.Connect(120);
            var bytes = Encoding.UTF8.GetBytes(payload);
            client.Write(bytes, 0, bytes.Length);
            client.Flush();
            return true;
        }
        catch
        {
            return false;
        }
    }

    public static bool SendThemeCmd(string panelDir, string themeKey)
    {
        if (string.IsNullOrWhiteSpace(themeKey))
            return false;
        bool pipeOk = TrySendPipe($"theme {themeKey}\n");
        if (pipeOk)
            return true;
        try
        {
            File.WriteAllText(Path.Combine(panelDir, "theme_cmd.txt"), themeKey, new UTF8Encoding(false));
            return true;
        }
        catch
        {
            return false;
        }
    }

    public static bool SendPanelCmd(string panelDir, params string[] lines)
    {
        if (lines.Length == 0)
            return false;
        var payload = string.Join("\n", lines) + "\n";
        if (TrySendPipe(payload))
            return true;
        try
        {
            File.AppendAllText(Path.Combine(panelDir, "panel_cmd.txt"), payload, new UTF8Encoding(false));
            return true;
        }
        catch
        {
            return false;
        }
    }

    public static (bool Ok, string? Error) LaunchPanel(string panelDir, bool asAdmin = true, string? args = null)
    {
        var exe = Path.Combine(panelDir, PanelExeName);
        if (!File.Exists(exe))
            return (false, $"{PanelExeName} introuvable dans {panelDir}");

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = exe,
                Arguments = args ?? "",
                WorkingDirectory = panelDir,
                UseShellExecute = true,
                Verb = asAdmin ? "runas" : "",
                WindowStyle = ProcessWindowStyle.Normal,
            };
            Process.Start(psi);
            return (true, null);
        }
        catch (System.ComponentModel.Win32Exception ex) when (ex.NativeErrorCode == 1223)
        {
            return (false, "Lancement administrateur refusé (UAC annulé)");
        }
        catch (Exception ex)
        {
            return (false, ex.Message);
        }
    }

    public static async Task<bool> StopPanelAsync(string panelDir, int waitMs = 2500)
    {
        if (!IsPanelRunning())
            return true;

        SendPanelCmd(panelDir, "quit");
        var sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < waitMs)
        {
            if (!IsPanelRunning())
                return true;
            await Task.Delay(120);
        }

        // Secours si le processus ne répond pas (même niveau de privilèges)
        foreach (var p in Process.GetProcessesByName("Moniteur"))
        {
            try
            {
                p.Kill(entireProcessTree: true);
            }
            catch { }
            finally
            {
                p.Dispose();
            }
        }

        await Task.Delay(250);
        return !IsPanelRunning();
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr FindWindowW(string? lpClassName, string? lpWindowName);

    [DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hWnd);

    public static bool FocusExistingWindow(string title)
    {
        var hwnd = FindWindowW(null, title);
        if (hwnd == IntPtr.Zero)
            return false;
        ShowWindow(hwnd, 9); // SW_RESTORE
        SetForegroundWindow(hwnd);
        return true;
    }
}
