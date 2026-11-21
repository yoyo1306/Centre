using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Win32;

namespace CentreControle.Core;

public static class PawnIoHelper
{
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr OpenSCManagerW(string? lpMachineName, string? lpDatabaseName, uint dwDesiredAccess);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr OpenServiceW(IntPtr hSCManager, string lpServiceName, uint dwDesiredAccess);

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern bool CloseServiceHandle(IntPtr hSCObject);

    public static bool IsInstalled()
    {
        try
        {
            using var hklm = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64);
            using var key = hklm.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO");
            var loc = key?.GetValue("InstallLocation") as string;
            if (string.IsNullOrWhiteSpace(loc) || !File.Exists(Path.Combine(loc, "PawnIOLib.dll")))
                return false;
        }
        catch
        {
            return false;
        }

        IntPtr scm = OpenSCManagerW(null, null, 0x0001); // SC_MANAGER_CONNECT
        if (scm == IntPtr.Zero)
            return false;
        try
        {
            IntPtr svc = OpenServiceW(scm, "PawnIO", 0x0004); // SERVICE_QUERY_STATUS
            if (svc == IntPtr.Zero)
                return false;
            CloseServiceHandle(svc);
            return true;
        }
        finally
        {
            CloseServiceHandle(scm);
        }
    }

    public static string? GetDisplayVersion()
    {
        try
        {
            using var hklm = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64);
            using var key = hklm.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO");
            var loc = key?.GetValue("InstallLocation") as string;
            if (!string.IsNullOrWhiteSpace(loc))
            {
                var dll = Path.Combine(loc, "PawnIOLib.dll");
                if (File.Exists(dll))
                {
                    var vi = FileVersionInfo.GetVersionInfo(dll);
                    if (!string.IsNullOrWhiteSpace(vi.FileVersion))
                        return vi.FileVersion;
                }
            }
        }
        catch { }
        return null;
    }

    public static bool EnsureInstalled(string libsDir)
    {
        if (IsInstalled())
            return true;

        var setup = Path.Combine(libsDir, "PawnIO_setup.exe");
        if (!File.Exists(setup))
            return false;

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = setup,
                Arguments = "-install -silent",
                WorkingDirectory = libsDir,
                UseShellExecute = !PanelIpc.IsAdmin(),
                Verb = PanelIpc.IsAdmin() ? "" : "runas",
                CreateNoWindow = PanelIpc.IsAdmin(),
                WindowStyle = ProcessWindowStyle.Hidden,
            };
            using var proc = Process.Start(psi);
            proc?.WaitForExit(90_000);
        }
        catch { }

        return IsInstalled();
    }
}
