using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using CentreControle.Core;
using CentreControle.Monitor.Themes;

namespace CentreControle.Monitor;

public sealed class PanelForm : Form
{
    private readonly string _baseDir;
    private readonly string _dataDir;
    private readonly string _cfgPath;
    private readonly HardwareSensors _sensors;
    private readonly ThemeDrawContext _drawCtx;
    private readonly SensorState _state;
    private readonly System.Windows.Forms.Timer _sampleTimer;
    private readonly System.Windows.Forms.Timer _cmdTimer;
    private readonly System.Windows.Forms.Timer _savePosTimer;
    private readonly CancellationTokenSource _pipeCts = new();
    private bool _disposed;

    private IPanelTheme _theme;
    private bool _locked;
    private bool _topmost;
    private bool _wantCpuTemp;
    private DateTime _lastCfgMtime;
    private Point _lastSavedPos;
    private bool _dragging;
    private Point _dragStart;
    private readonly string? _screenshotPath;

    private static readonly IntPtr HWND_TOPMOST = new(-1);
    private static readonly IntPtr HWND_NOTOPMOST = new(-2);
    private const uint SWP_NOMOVE = 0x0002;
    private const uint SWP_NOSIZE = 0x0001;
    private const uint SWP_NOACTIVATE = 0x0010;

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);

    public PanelForm(string baseDir, string? themeArg, bool setupMode, int? selftestMs, string? screenshotPath)
    {
        _baseDir = baseDir;
        _dataDir = AppPaths.ResolveDataDir(baseDir);
        _cfgPath = Path.Combine(_dataDir, PanelIpc.PanelConfigName);
        _screenshotPath = screenshotPath;

        var cfg = IniConfig.Read(_cfgPath);
        _lastCfgMtime = File.Exists(_cfgPath) ? File.GetLastWriteTimeUtc(_cfgPath) : DateTime.MinValue;

        _locked = !setupMode && IniConfig.GetBool(cfg, "panel", "locked", true);
        _topmost = IniConfig.GetBool(cfg, "panel", "topmost", true);
        _wantCpuTemp = IniConfig.GetBool(cfg, "panel", "cpu_temp_lhm", true);

        int intervalMs = Math.Max(100, IniConfig.GetInt(cfg, "panel", "interval_ms", 1000));
        string speed = IniConfig.GetString(cfg, "panel", "update_speed", "").Trim().ToLowerInvariant();
        bool paused = false;
        int histCap = Math.Max(2, IniConfig.GetInt(cfg, "panel", "history", 300));
        if (speed == "paused")
        {
            paused = true;
        }
        else if (speed is "high" or "normal" or "low")
        {
            intervalMs = ThemeCatalog.SpeedIntervalMs(speed, intervalMs);
            histCap = Math.Max(2, (int)Math.Round((double)ThemeCatalog.HistoryWindowMs / intervalMs));
        }

        _state = new SensorState(histCap)
        {
            IntervalMs = intervalMs,
            Paused = paused,
        };

        _drawCtx = new ThemeDrawContext(baseDir);
        _drawCtx.Colors = new PaletteColors
        {
            Label = PaletteColors.Parse(IniConfig.GetString(cfg, "colors", "label"), _drawCtx.Colors.Label),
            Value = PaletteColors.Parse(IniConfig.GetString(cfg, "colors", "value"), _drawCtx.Colors.Value),
            Graph = PaletteColors.Parse(IniConfig.GetString(cfg, "colors", "graph"), _drawCtx.Colors.Graph),
            Graph2 = PaletteColors.Parse(IniConfig.GetString(cfg, "colors", "graph2"), _drawCtx.Colors.Graph2),
            Grid = PaletteColors.Parse(IniConfig.GetString(cfg, "colors", "grid"), _drawCtx.Colors.Grid),
            Frame = PaletteColors.Parse(IniConfig.GetString(cfg, "colors", "frame"), _drawCtx.Colors.Frame),
            Background = PaletteColors.Parse(IniConfig.GetString(cfg, "colors", "bg"), _drawCtx.Colors.Background),
        };

        string themeKey = !string.IsNullOrWhiteSpace(themeArg)
            ? themeArg
            : IniConfig.GetString(cfg, "panel", "theme", "01-aida");
        _theme = ThemeFactory.Create(themeKey);

        _sensors = new HardwareSensors();
        _sensors.Initialize(Path.Combine(baseDir, "libs"), _wantCpuTemp);

        // Efface ancienne commande panel_cmd.txt avant de démarrer
        try { File.Delete(Path.Combine(_dataDir, "panel_cmd.txt")); } catch { }

        // Propriétés fenêtre
        Text = "Moniteur";
        AutoScaleMode = AutoScaleMode.None;
        StartPosition = FormStartPosition.Manual;
        ClientSize = new Size(ThemeCatalog.PanelWidth, ThemeCatalog.PanelHeight);
        BackColor = Color.Black;
        DoubleBuffered = true;
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer, true);
        KeyPreview = true;

        var icoPath = Path.Combine(baseDir, "ico.ico");
        if (File.Exists(icoPath))
        {
            try { Icon = new Icon(icoPath); } catch { }
        }

        if (selftestMs.HasValue)
            _locked = true;

        ApplyWindowChrome();
        var (px, py) = ResolveInitialPosition(cfg, selftestMs.HasValue);
        Location = new Point(px, py);
        _lastSavedPos = Location;

        MouseDown += OnPanelMouseDown;
        MouseMove += OnPanelMouseMove;
        MouseUp += OnPanelMouseUp;
        Move += OnPanelMove;
        KeyDown += (_, e) =>
        {
            if (e.KeyCode == Keys.Escape)
                Close();
        };

        _savePosTimer = new System.Windows.Forms.Timer { Interval = 400 };
        _savePosTimer.Tick += (_, _) =>
        {
            _savePosTimer.Stop();
            SavePositionToIni(Location.X, Location.Y);
        };

        _sampleTimer = new System.Windows.Forms.Timer { Interval = Math.Max(100, _state.IntervalMs) };
        _sampleTimer.Tick += (_, _) => SampleAndRender();

        _cmdTimer = new System.Windows.Forms.Timer { Interval = 250 };
        _cmdTimer.Tick += (_, _) => PollFileCommandsAndConfig();

        Shown += (_, _) =>
        {
            ApplyTopmost(_topmost);
            SampleAndRender();
            _sampleTimer.Start();
            _cmdTimer.Start();
            StartPipeServer();

            if (!string.IsNullOrWhiteSpace(_screenshotPath))
            {
                SaveScreenshot(_screenshotPath);
            }

            if (selftestMs.HasValue && selftestMs.Value > 0)
            {
                var st = new System.Windows.Forms.Timer { Interval = selftestMs.Value };
                st.Tick += (_, _) =>
                {
                    st.Stop();
                    if (!string.IsNullOrWhiteSpace(_screenshotPath))
                        SaveScreenshot(_screenshotPath);
                    Close();
                };
                st.Start();
            }
        };
    }

    private (int X, int Y) ResolveInitialPosition(Dictionary<string, Dictionary<string, string>> cfg, bool selftest)
    {
        if (selftest)
            return (60, 60);

        string sx = IniConfig.GetString(cfg, "panel", "x", "").Trim();
        string sy = IniConfig.GetString(cfg, "panel", "y", "").Trim();
        if (int.TryParse(sx, out int cx) && int.TryParse(sy, out int cy))
        {
            var mons = MonitorHelper.GetAllMonitors();
            bool visibleOnAny = mons.Count == 0 || mons.Any(m =>
                cx + ThemeCatalog.PanelWidth > m.X && cx < m.X + m.Width &&
                cy + ThemeCatalog.PanelHeight > m.Y && cy < m.Y + m.Height);
            if (visibleOnAny)
                return (cx, cy);
        }

        var (tx, ty, _) = MonitorHelper.GetCenteredPanelPosition();
        return (tx, ty);
    }

    private void ApplyWindowChrome()
    {
        FormBorderStyle = _locked ? FormBorderStyle.None : FormBorderStyle.FixedToolWindow;
        ShowInTaskbar = !_locked;
        ClientSize = new Size(ThemeCatalog.PanelWidth, ThemeCatalog.PanelHeight);
        TopMost = _topmost;
    }

    private void ApplyTopmost(bool value)
    {
        _topmost = value;
        TopMost = value;
        if (IsHandleCreated)
        {
            SetWindowPos(Handle, value ? HWND_TOPMOST : HWND_NOTOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
        }
    }

    private void SampleAndRender()
    {
        if (!_state.Paused)
            _sensors.SampleInto(_state, _wantCpuTemp);
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;
        g.PixelOffsetMode = PixelOffsetMode.HighQuality;
        _theme.Render(g, _drawCtx, _state);
    }

    private void SaveScreenshot(string path)
    {
        try
        {
            var dir = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(dir))
                Directory.CreateDirectory(dir);
            using var bmp = new Bitmap(ThemeCatalog.PanelWidth, ThemeCatalog.PanelHeight);
            using (var g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;
                g.PixelOffsetMode = PixelOffsetMode.HighQuality;
                _theme.Render(g, _drawCtx, _state);
            }
            bmp.Save(path, ImageFormat.Png);
        }
        catch { }
    }

    private void OnPanelMouseDown(object? sender, MouseEventArgs e)
    {
        if (!_locked && e.Button == MouseButtons.Left)
        {
            _dragging = true;
            _dragStart = e.Location;
        }
    }

    private void OnPanelMouseMove(object? sender, MouseEventArgs e)
    {
        if (_dragging && !_locked)
        {
            Location = new Point(Location.X + e.X - _dragStart.X, Location.Y + e.Y - _dragStart.Y);
        }
    }

    private void OnPanelMouseUp(object? sender, MouseEventArgs e)
    {
        if (_dragging)
        {
            _dragging = false;
            _savePosTimer.Stop();
            _savePosTimer.Start();
        }
    }

    private void OnPanelMove(object? sender, EventArgs e)
    {
        if (_locked || !IsHandleCreated) return;
        if (Location != _lastSavedPos)
        {
            _savePosTimer.Stop();
            _savePosTimer.Start();
        }
    }

    private void SavePositionToIni(int x, int y)
    {
        _lastSavedPos = new Point(x, y);
        IniConfig.PatchSection(_cfgPath, "panel", new Dictionary<string, string>
        {
            ["x"] = x.ToString(),
            ["y"] = y.ToString(),
        });
        if (File.Exists(_cfgPath))
            _lastCfgMtime = File.GetLastWriteTimeUtc(_cfgPath);
    }

    private void StartPipeServer()
    {
        _ = Task.Run(async () =>
        {
            var ps = new PipeSecurity();
            ps.AddAccessRule(new PipeAccessRule(
                new SecurityIdentifier(WellKnownSidType.AuthenticatedUserSid, null),
                PipeAccessRights.ReadWrite,
                AccessControlType.Allow));

            while (!_pipeCts.IsCancellationRequested)
            {
                try
                {
                    await using var server = NamedPipeServerStreamAcl.Create(
                        PanelIpc.PipeName,
                        PipeDirection.In,
                        NamedPipeServerStream.MaxAllowedServerInstances,
                        PipeTransmissionMode.Byte,
                        PipeOptions.Asynchronous,
                        0, 0, ps);

                    await server.WaitForConnectionAsync(_pipeCts.Token);
                    using var reader = new StreamReader(server, Encoding.UTF8);
                    var content = await reader.ReadToEndAsync(_pipeCts.Token);
                    if (!string.IsNullOrWhiteSpace(content) && !IsDisposed)
                    {
                        BeginInvoke(() => HandleCommandLines(content.Split('\n', StringSplitOptions.RemoveEmptyEntries)));
                    }
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                catch
                {
                    await Task.Delay(250);
                }
            }
        });
    }

    private void PollFileCommandsAndConfig()
    {
        // theme_cmd.txt
        var themeFile = Path.Combine(_dataDir, "theme_cmd.txt");
        if (File.Exists(themeFile))
        {
            try
            {
                var key = File.ReadAllText(themeFile, Encoding.UTF8).Trim().TrimStart('\uFEFF');
                File.Delete(themeFile);
                if (!string.IsNullOrWhiteSpace(key))
                    ApplyTheme(key);
            }
            catch { }
        }

        // panel_cmd.txt
        var cmdFile = Path.Combine(_dataDir, "panel_cmd.txt");
        if (File.Exists(cmdFile))
        {
            try
            {
                var lines = File.ReadAllLines(cmdFile, Encoding.UTF8);
                File.Delete(cmdFile);
                HandleCommandLines(lines);
            }
            catch { }
        }

        // config.ini live speed reload
        try
        {
            if (File.Exists(_cfgPath))
            {
                var mtime = File.GetLastWriteTimeUtc(_cfgPath);
                if (mtime != _lastCfgMtime)
                {
                    _lastCfgMtime = mtime;
                    ReloadSpeedFromConfig();
                }
            }
        }
        catch { }
    }

    private void ReloadSpeedFromConfig()
    {
        var cfg = IniConfig.Read(_cfgPath);
        string speed = IniConfig.GetString(cfg, "panel", "update_speed", "").Trim().ToLowerInvariant();
        if (speed == "paused")
        {
            _state.Paused = true;
            Invalidate();
        }
        else if (speed is "high" or "normal" or "low")
        {
            int ms = ThemeCatalog.SpeedIntervalMs(speed, 1000);
            _state.Paused = false;
            _state.IntervalMs = ms;
            _state.ResizeHistory(Math.Max(2, (int)Math.Round((double)ThemeCatalog.HistoryWindowMs / ms)));
            _sampleTimer.Interval = Math.Max(100, ms);
            Invalidate();
        }
    }

    private void HandleCommandLines(IEnumerable<string> rawLines)
    {
        foreach (var raw in rawLines)
        {
            var line = raw.Trim().TrimStart('\uFEFF');
            if (line.Length == 0) continue;
            var parts = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
            var cmd = parts[0].ToLowerInvariant();

            switch (cmd)
            {
                case "quit":
                    Close();
                    return;
                case "theme" when parts.Length >= 2:
                    ApplyTheme(parts[1]);
                    break;
                case "pos" when parts.Length >= 3 && int.TryParse(parts[1], out int nx) && int.TryParse(parts[2], out int ny):
                    Location = new Point(nx, ny);
                    _lastSavedPos = Location;
                    break;
                case "lock" when parts.Length >= 2:
                    bool wantLock = parts[1].ToLowerInvariant() is "1" or "true" or "yes" or "on";
                    if (wantLock != _locked)
                    {
                        var pos = Location;
                        _locked = wantLock;
                        ApplyWindowChrome();
                        Location = pos;
                        ApplyTopmost(_topmost);
                    }
                    break;
                case "topmost" when parts.Length >= 2:
                    bool wantTop = parts[1].ToLowerInvariant() is "1" or "true" or "yes" or "on";
                    ApplyTopmost(wantTop);
                    break;
            }
        }
    }

    private void ApplyTheme(string key)
    {
        _theme = ThemeFactory.Create(key);
        Invalidate();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing && !_disposed)
        {
            _disposed = true;
            try { _pipeCts.Cancel(); } catch { }
            _pipeCts.Dispose();
            _sampleTimer.Dispose();
            _cmdTimer.Dispose();
            _savePosTimer.Dispose();
            _sensors.Dispose();
            _drawCtx.Dispose();
        }
        base.Dispose(disposing);
    }
}
