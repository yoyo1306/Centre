using CentreControle.Core;
using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Graphics;
using Windows.System;
using WinRT.Interop;

namespace CentreControle.App;

public sealed partial class MainWindow : Window
{
    private readonly string _appDir;
    private readonly string _panelDir;
    private readonly string _dataDir;
    private readonly string _panelDataDir;
    private readonly string _centreIniPath;
    private readonly string _panelIniPath;

    private readonly DispatcherTimer _statusTimer;
    private readonly DispatcherTimer _brightTimer;
    private readonly DispatcherTimer _flashClearTimer;

    private readonly Button[] _brightButtons = new Button[6];
    private readonly Dictionary<string, Button> _speedButtons = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, (Button Card, Border Frame, Border ActiveBadge)> _themeCards = new(StringComparer.OrdinalIgnoreCase);

    private List<ThemeInfo> _visibleThemes = ThemeCatalog.All.ToList();
    private string _activeFilter = "all";
    private string _savedThemeKey = "01-aida";
    private string _selectedThemeKey = "01-aida";
    private string? _previewThemeKey;

    private int? _selectedBrightIndex;
    private DateTime _brightHoldUntil = DateTime.MinValue;
    private DateTime _lastPanelLaunch = DateTime.MinValue;

    private bool _suppressOptionEvents;
    private bool _isDark = true;
    private string _currentSpeed = "normal";

    public MainWindow()
    {
        InitializeComponent();

        _appDir = AppPaths.ResolveInstallDir();
        _dataDir = AppPaths.ResolveDataDir(_appDir);
        _centreIniPath = Path.Combine(_dataDir, "centre.ini");
        _panelDir = ResolvePanelDir(_appDir, _centreIniPath);
        _panelDataDir = AppPaths.ResolveDataDir(_panelDir);
        _panelIniPath = Path.Combine(_panelDataDir, PanelIpc.PanelConfigName);

        SoundHelper.Initialize(_appDir);

        // Backdrop Windows 11 Mica natif
        try { SystemBackdrop = new MicaBackdrop(); } catch { }

        // Barre de titre WinUI 3 personnalisée
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);

        ConfigureWindow();
        LoadInitialSettings();
        BuildBrightnessButtons();
        BuildSpeedButtons();
        ApplyFilter("all");

        // Son en deux temps sur Appliquer (appui gauche -> click_down.wav, relâchement Click -> click_up.wav)
        ApplyBtn.AddHandler(UIElement.PointerPressedEvent, new PointerEventHandler((_, args) =>
        {
            if (args.GetCurrentPoint(ApplyBtn).Properties.IsLeftButtonPressed)
                SoundHelper.PlayClickDown();
        }), true);

        VersionFooterText.Text = $"Centre de contrôle v{ThemeCatalog.AppVersion} · WinUI 3";

        _statusTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.2) };
        _statusTimer.Tick += (_, _) => RefreshPanelRunningStatus();
        _statusTimer.Start();

        _brightTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.8) };
        _brightTimer.Tick += (_, _) => _ = PollSmallBrightnessAsync();
        _brightTimer.Start();

        _flashClearTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(4.0) };
        _flashClearTimer.Tick += (_, _) =>
        {
            _flashClearTimer.Stop();
            FlashText.Text = _previewThemeKey is not null
                ? $"Prévisualisation · {ThemeCatalog.Resolve(_previewThemeKey).Name} (non enregistré)"
                : $"Thème actif · {ThemeCatalog.Resolve(_savedThemeKey).Name}";
        };

        Closed += MainWindow_Closed;

        RefreshPanelRunningStatus();
        _ = PollSmallBrightnessAsync();
        SetFlash($"Thème actif · {ThemeCatalog.Resolve(_savedThemeKey).Name}", clearLater: false);
    }

    private static string ResolvePanelDir(string appDir, string centreIni)
    {
        var cfg = IniConfig.Read(centreIni);
        var configured = IniConfig.GetString(cfg, "panel", "path", "").Trim();
        if (!string.IsNullOrWhiteSpace(configured) && File.Exists(Path.Combine(configured, PanelIpc.PanelExeName)))
            return configured;
        return appDir;
    }

    private void ConfigureWindow()
    {
        var hwnd = WindowNative.GetWindowHandle(this);
        var winId = Win32Interop.GetWindowIdFromWindow(hwnd);
        var appWin = AppWindow.GetFromWindowId(winId);

        var icoPath = Path.Combine(_appDir, "ico.ico");
        if (File.Exists(icoPath))
        {
            try
            {
                appWin.SetIcon(icoPath);
                TitleIcon.Source = new BitmapImage(new Uri(icoPath));
            }
            catch { }
        }

        if (appWin.Presenter is OverlappedPresenter presenter)
        {
            presenter.IsMaximizable = false;
            presenter.IsResizable = true;
        }

        const int winW = 610;
        const int winH = 690;
        appWin.Resize(new SizeInt32(winW, winH));

        var cfg = IniConfig.Read(_centreIniPath);
        int savedX = IniConfig.GetInt(cfg, "centre", "x", -1);
        int savedY = IniConfig.GetInt(cfg, "centre", "y", -1);
        var (pw, ph) = MonitorHelper.GetPrimarySize();

        if (savedX >= 0 && savedY >= 0 && savedX < pw - 100 && savedY < ph - 100)
            appWin.Move(new PointInt32(savedX, savedY));
        else
            appWin.Move(new PointInt32(Math.Max(0, (pw - winW) / 2), Math.Max(0, (ph - winH) / 2)));
    }

    private void LoadInitialSettings()
    {
        var cCfg = IniConfig.Read(_centreIniPath);
        string appMode = IniConfig.GetString(cCfg, "centre", "appearance", "dark").Trim().ToLowerInvariant();
        _isDark = appMode != "light";
        ApplyThemeAppearance();

        var pCfg = IniConfig.Read(_panelIniPath);
        _savedThemeKey = ThemeCatalog.Resolve(IniConfig.GetString(pCfg, "panel", "theme", "01-aida")).Key;
        _selectedThemeKey = _savedThemeKey;
        _currentSpeed = IniConfig.GetString(pCfg, "panel", "update_speed", "normal").Trim().ToLowerInvariant();
        if (!ThemeCatalog.Speeds.Any(s => s.Key == _currentSpeed))
            _currentSpeed = "normal";
    }

    private void ApplyThemeAppearance()
    {
        RootGrid.RequestedTheme = _isDark ? ElementTheme.Dark : ElementTheme.Light;
        ThemeModeIcon.Glyph = _isDark ? "\uE706" : "\uE708";

        var hwnd = WindowNative.GetWindowHandle(this);
        var appWin = AppWindow.GetFromWindowId(Win32Interop.GetWindowIdFromWindow(hwnd));
        if (AppWindowTitleBar.IsCustomizationSupported())
        {
            var tb = appWin.TitleBar;
            tb.ButtonBackgroundColor = Colors.Transparent;
            tb.ButtonInactiveBackgroundColor = Colors.Transparent;
            tb.ButtonForegroundColor = _isDark ? Colors.White : Colors.Black;
        }

        if (_themeCards.Count > 0)
            UpdateThemeCardHighlights();
    }

    private void BuildBrightnessButtons()
    {
        BrightButtonsGrid.Children.Clear();
        for (int i = 0; i < ThemeCatalog.BrightnessLevels.Length; i++)
        {
            int idx = i;
            int pct = ThemeCatalog.BrightnessLevels[i];
            var btn = new Button
            {
                Content = $"{i}",
                HorizontalAlignment = HorizontalAlignment.Stretch,
                CornerRadius = new CornerRadius(6),
                Padding = new Thickness(0, 6, 0, 6),
                Tag = idx,
            };
            ToolTipService.SetToolTip(btn, $"Luminosité {pct} %");
            btn.Click += (_, _) => OnBrightnessSelected(idx);
            Grid.SetColumn(btn, i);
            BrightButtonsGrid.Children.Add(btn);
            _brightButtons[i] = btn;
        }
        UpdateBrightnessVisuals();
    }

    private void UpdateBrightnessVisuals()
    {
        var accentStyle = (Style)Application.Current.Resources["AccentButtonStyle"];
        var defaultStyle = (Style)Application.Current.Resources["DefaultButtonStyle"];
        for (int i = 0; i < _brightButtons.Length; i++)
        {
            _brightButtons[i].Style = _selectedBrightIndex == i ? accentStyle : defaultStyle;
        }

        if (_selectedBrightIndex is int sel && sel >= 0 && sel < ThemeCatalog.BrightnessLevels.Length)
            BrightValueText.Text = $"{ThemeCatalog.BrightnessLevels[sel]} %";
        else
            BrightValueText.Text = MonitorHelper.HasSmallMonitor() ? "Synchronisation…" : "Écran 480×320 non détecté";
    }

    private void OnBrightnessSelected(int idx)
    {
        _selectedBrightIndex = idx;
        _brightHoldUntil = DateTime.UtcNow.AddSeconds(1.6);
        int pct = ThemeCatalog.BrightnessLevels[idx];
        UpdateBrightnessVisuals();

        _ = Task.Run(() =>
        {
            bool ok = MonitorHelper.ApplySmallBrightness(pct);
            DispatcherQueue.TryEnqueue(() =>
            {
                if (!ok)
                    SetFlash("Luminosité refusée (écran 480×320 absent ou DDC/CI inactif)");
                else
                    SetFlash($"Luminosité réglée sur {pct} %");
            });
        });
    }

    private async Task PollSmallBrightnessAsync()
    {
        if (DateTime.UtcNow < _brightHoldUntil)
            return;

        int? pct = await Task.Run(MonitorHelper.ReadSmallBrightness);
        if (DateTime.UtcNow < _brightHoldUntil)
            return;

        if (pct is int value)
        {
            int bestIdx = 0;
            int bestDiff = int.MaxValue;
            for (int i = 0; i < ThemeCatalog.BrightnessLevels.Length; i++)
            {
                int d = Math.Abs(ThemeCatalog.BrightnessLevels[i] - value);
                if (d < bestDiff)
                {
                    bestDiff = d;
                    bestIdx = i;
                }
            }
            if (_selectedBrightIndex != bestIdx)
            {
                _selectedBrightIndex = bestIdx;
                UpdateBrightnessVisuals();
            }
        }
        else if (_selectedBrightIndex is null)
        {
            UpdateBrightnessVisuals();
        }
    }

    private void BuildSpeedButtons()
    {
        SpeedButtonsGrid.Children.Clear();
        _speedButtons.Clear();
        for (int i = 0; i < ThemeCatalog.Speeds.Count; i++)
        {
            var sp = ThemeCatalog.Speeds[i];
            var btn = new Button
            {
                Content = sp.Label,
                HorizontalAlignment = HorizontalAlignment.Stretch,
                CornerRadius = new CornerRadius(6),
                Padding = new Thickness(6, 6, 6, 6),
                FontSize = 12,
                Tag = sp.Key,
            };
            btn.Click += (_, _) => OnSpeedSelected(sp);
            Grid.SetColumn(btn, i);
            SpeedButtonsGrid.Children.Add(btn);
            _speedButtons[sp.Key] = btn;
        }
        UpdateSpeedVisuals();
    }

    private void UpdateSpeedVisuals()
    {
        var accentStyle = (Style)Application.Current.Resources["AccentButtonStyle"];
        var defaultStyle = (Style)Application.Current.Resources["DefaultButtonStyle"];
        foreach (var (key, btn) in _speedButtons)
            btn.Style = key.Equals(_currentSpeed, StringComparison.OrdinalIgnoreCase) ? accentStyle : defaultStyle;
    }

    private void OnSpeedSelected(SpeedOption sp)
    {
        var updates = new Dictionary<string, string>
        {
            ["update_speed"] = sp.Key,
        };
        if (sp.IntervalMs > 0)
        {
            updates["interval_ms"] = sp.IntervalMs.ToString();
            updates["history"] = Math.Max(2, (int)Math.Round((double)ThemeCatalog.HistoryWindowMs / sp.IntervalMs)).ToString();
        }
        if (IniConfig.PatchSection(_panelIniPath, "panel", updates))
        {
            _currentSpeed = sp.Key;
            UpdateSpeedVisuals();
            SetFlash($"Vitesse : {sp.Label}");
        }
        else
        {
            SetFlash("Écriture config.ini refusée");
        }
    }

    private void ApplyFilter(string filter)
    {
        _activeFilter = filter;
        _visibleThemes = filter switch
        {
            "green" => ThemeCatalog.All.Where(t => t.IsGreen).ToList(),
            "color" => ThemeCatalog.All.Where(t => !t.IsGreen).ToList(),
            _ => ThemeCatalog.All.ToList(),
        };

        var accentStyle = (Style)Application.Current.Resources["AccentButtonStyle"];
        var defaultStyle = (Style)Application.Current.Resources["DefaultButtonStyle"];
        FilterAllBtn.Style = filter == "all" ? accentStyle : defaultStyle;
        FilterGreenBtn.Style = filter == "green" ? accentStyle : defaultStyle;
        FilterColorBtn.Style = filter == "color" ? accentStyle : defaultStyle;

        ThemeCountText.Text = $"({_visibleThemes.Count})";
        RebuildThemeGrid();
    }

    private void RebuildThemeGrid()
    {
        ThemesHostGrid.Children.Clear();
        ThemesHostGrid.RowDefinitions.Clear();
        _themeCards.Clear();

        int rows = (_visibleThemes.Count + 2) / 3;
        for (int r = 0; r < rows; r++)
            ThemesHostGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

        for (int i = 0; i < _visibleThemes.Count; i++)
        {
            var theme = _visibleThemes[i];
            int row = i / 3;
            int col = i % 3;

            var cardGrid = new Grid { RowSpacing = 6 };
            cardGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            cardGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

            // Vignette 480x320 complète (ratio 3:2 exact sans rognage)
            var imgContainer = new Grid
            {
                CornerRadius = new CornerRadius(6),
                Background = new SolidColorBrush(Colors.Black),
                Height = 110,
            };

            var imgPath = Path.Combine(_panelDir, theme.PreviewRelativePath);
            if (!File.Exists(imgPath))
                imgPath = Path.Combine(_appDir, theme.PreviewRelativePath);
            if (File.Exists(imgPath))
            {
                var bmp = new BitmapImage(new Uri(imgPath)) { DecodePixelWidth = 360 };
                imgContainer.Children.Add(new Image
                {
                    Source = bmp,
                    Stretch = Stretch.Uniform,
                });
            }

            Grid.SetRow(imgContainer, 0);
            cardGrid.Children.Add(imgContainer);

            var activeBadge = new Border
            {
                Background = (Brush)Application.Current.Resources["AccentFillColorDefaultBrush"],
                CornerRadius = new CornerRadius(4),
                Padding = new Thickness(5, 1, 5, 1),
                VerticalAlignment = VerticalAlignment.Center,
                Visibility = theme.Key == _savedThemeKey ? Visibility.Visible : Visibility.Collapsed,
                Child = new TextBlock
                {
                    Text = "Actif",
                    FontSize = 10,
                    FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
                    Foreground = (Brush)Application.Current.Resources["TextOnAccentFillColorPrimaryBrush"],
                },
            };

            var captionRow = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Spacing = 6,
                HorizontalAlignment = HorizontalAlignment.Center,
                VerticalAlignment = VerticalAlignment.Center,
            };
            captionRow.Children.Add(new TextBlock
            {
                Text = theme.Name,
                FontSize = 12,
                TextTrimming = TextTrimming.CharacterEllipsis,
                VerticalAlignment = VerticalAlignment.Center,
            });
            captionRow.Children.Add(activeBadge);

            Grid.SetRow(captionRow, 1);
            cardGrid.Children.Add(captionRow);

            var frame = new Border
            {
                CornerRadius = new CornerRadius(8),
                BorderThickness = new Thickness(2),
                Padding = new Thickness(6),
                Child = cardGrid,
            };

            var btn = new Button
            {
                Content = frame,
                Padding = new Thickness(0),
                BorderThickness = new Thickness(0),
                Background = new SolidColorBrush(Colors.Transparent),
                HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
                CornerRadius = new CornerRadius(8),
            };
            // Button.Click dans WinUI 3 se déclenche au relâchement du clic sur le même élément
            btn.Click += (_, _) => OnThemeClicked(theme);

            Grid.SetRow(btn, row);
            Grid.SetColumn(btn, col);
            ThemesHostGrid.Children.Add(btn);
            _themeCards[theme.Key] = (btn, frame, activeBadge);
        }

        UpdateThemeCardHighlights();
    }

    private void UpdateThemeCardHighlights()
    {
        var accentBrush = (Brush)Application.Current.Resources["AccentFillColorDefaultBrush"];
        var normalBorder = new SolidColorBrush(_isDark
            ? Windows.UI.Color.FromArgb(24, 255, 255, 255)
            : Windows.UI.Color.FromArgb(22, 0, 0, 0));
        var cardBg = new SolidColorBrush(_isDark
            ? Windows.UI.Color.FromArgb(14, 255, 255, 255)
            : Windows.UI.Color.FromArgb(180, 255, 255, 255));
        var selectedBg = new SolidColorBrush(_isDark
            ? Windows.UI.Color.FromArgb(26, 255, 255, 255)
            : Windows.UI.Color.FromArgb(235, 255, 255, 255));

        foreach (var (key, item) in _themeCards)
        {
            bool selected = key.Equals(_selectedThemeKey, StringComparison.OrdinalIgnoreCase);
            bool saved = key.Equals(_savedThemeKey, StringComparison.OrdinalIgnoreCase);
            item.Frame.BorderBrush = selected ? accentBrush : normalBorder;
            item.Frame.Background = selected ? selectedBg : cardBg;
            item.ActiveBadge.Visibility = saved ? Visibility.Visible : Visibility.Collapsed;
        }
    }

    private void OnThemeClicked(ThemeInfo theme)
    {
        _selectedThemeKey = theme.Key;
        UpdateThemeCardHighlights();
        PreviewTheme(theme);
    }

    private void PreviewTheme(ThemeInfo theme)
    {
        _previewThemeKey = theme.Key;
        if (!PanelIpc.SendThemeCmd(_panelDataDir, theme.Key))
        {
            SetFlash("Prévisualisation impossible");
            return;
        }

        if (PanelIpc.IsPanelRunning())
        {
            SetFlash($"Prévisualisation · {theme.Name}");
            return;
        }

        if ((DateTime.UtcNow - _lastPanelLaunch).TotalSeconds < 2.0)
        {
            SetFlash($"Prévisualisation · {theme.Name}");
            return;
        }

        _lastPanelLaunch = DateTime.UtcNow;
        var (ok, err) = PanelIpc.LaunchPanel(_panelDir, asAdmin: true, args: $"--theme={theme.Key}");
        if (ok)
        {
            SetFlash($"Prévisualisation · {theme.Name}");
            RefreshPanelRunningStatus();
        }
        else
        {
            SetFlash(err ?? "Lancement du moniteur impossible");
        }
    }

    private void ApplyBtn_Click(object sender, RoutedEventArgs e)
    {
        SoundHelper.PlayClickUp();

        var chosen = ThemeCatalog.Resolve(_selectedThemeKey);
        if (!IniConfig.PatchSection(_panelIniPath, "panel", new Dictionary<string, string> { ["theme"] = chosen.Key }))
        {
            SetFlash("Écriture config.ini refusée");
            return;
        }

        _savedThemeKey = chosen.Key;
        _previewThemeKey = null;
        UpdateThemeCardHighlights();

        if (PanelIpc.IsPanelRunning())
        {
            PanelIpc.SendThemeCmd(_panelDataDir, chosen.Key);
            SetFlash($"Thème appliqué · {chosen.Name}");
        }
        else
        {
            _lastPanelLaunch = DateTime.UtcNow;
            var (ok, err) = PanelIpc.LaunchPanel(_panelDir, asAdmin: true);
            SetFlash(ok ? $"Thème appliqué · {chosen.Name}" : (err ?? "Lancement impossible"));
            RefreshPanelRunningStatus();
        }
    }

    private async void StopBtn_Click(object sender, RoutedEventArgs e)
    {
        StopBtn.IsEnabled = false;
        _previewThemeKey = null;
        bool stopped = await PanelIpc.StopPanelAsync(_panelDataDir);
        StopBtn.IsEnabled = true;
        RefreshPanelRunningStatus();
        SetFlash(stopped ? "Moniteur arrêté" : "Arrêt refusé (droits administrateur requis)");
    }

    private void RefreshPanelRunningStatus()
    {
        bool running = PanelIpc.IsPanelRunning();
        StatusLabel.Text = running ? "Moniteur actif" : "Arrêté";
        StatusDot.Fill = running
            ? new SolidColorBrush(Windows.UI.Color.FromArgb(255, 52, 211, 153))
            : (Brush)Application.Current.Resources["TextFillColorTertiaryBrush"];
        StopBtn.IsEnabled = running;
    }

    private void ThemeModeBtn_Click(object sender, RoutedEventArgs e)
    {
        _isDark = !_isDark;
        ApplyThemeAppearance();
        IniConfig.PatchSection(_centreIniPath, "centre", new Dictionary<string, string>
        {
            ["appearance"] = _isDark ? "dark" : "light",
        });
    }

    private void FilterBtn_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button b && b.Tag is string f)
            ApplyFilter(f);
    }

    private void OptionsToggleBtn_Click(object sender, RoutedEventArgs e)
    {
        bool open = OptionsToggleBtn.IsChecked == true;
        OptionsOverlay.Visibility = open ? Visibility.Visible : Visibility.Collapsed;
        if (open)
            RefreshOptionsState();
    }

    private void CloseOptionsBtn_Click(object sender, RoutedEventArgs e)
    {
        OptionsToggleBtn.IsChecked = false;
        OptionsOverlay.Visibility = Visibility.Collapsed;
    }

    private void RefreshOptionsState()
    {
        _suppressOptionEvents = true;
        try
        {
            var pCfg = IniConfig.Read(_panelIniPath);
            LockToggle.IsOn = IniConfig.GetBool(pCfg, "panel", "locked", true);
            TopmostToggle.IsOn = IniConfig.GetBool(pCfg, "panel", "topmost", true);
            _currentSpeed = IniConfig.GetString(pCfg, "panel", "update_speed", "normal").Trim().ToLowerInvariant();
            UpdateSpeedVisuals();
            StartupToggle.IsOn = StartupTask.IsEnabled();

            bool pawnOk = PawnIoHelper.IsInstalled();
            string? pawnVer = pawnOk ? PawnIoHelper.GetDisplayVersion() : null;
            PawnIoStatusText.Text = pawnOk
                ? $"Installé{(string.IsNullOrWhiteSpace(pawnVer) ? "" : $" · v{pawnVer}")}"
                : "Absent — installé automatiquement au lancement du Moniteur";
            InstallPawnIoBtn.Visibility = pawnOk ? Visibility.Collapsed : Visibility.Visible;
        }
        finally
        {
            _suppressOptionEvents = false;
        }
    }

    private async void StartupToggle_Toggled(object sender, RoutedEventArgs e)
    {
        if (_suppressOptionEvents) return;
        bool want = StartupToggle.IsOn;
        StartupToggle.IsEnabled = false;
        var exePath = Path.Combine(_panelDir, PanelIpc.PanelExeName);
        var (ok, err) = await StartupTask.SetEnabledAsync(want, exePath);
        _suppressOptionEvents = true;
        StartupToggle.IsOn = StartupTask.IsEnabled();
        _suppressOptionEvents = false;
        StartupToggle.IsEnabled = true;
        SetFlash(ok
            ? (want ? "Démarrage automatique activé" : "Démarrage automatique désactivé")
            : (err ?? "Modification refusée"));
    }

    private void RecenterBtn_Click(object sender, RoutedEventArgs e)
    {
        var (tx, ty, label) = MonitorHelper.GetCenteredPanelPosition();
        if (!IniConfig.PatchSection(_panelIniPath, "panel", new Dictionary<string, string>
        {
            ["x"] = tx.ToString(),
            ["y"] = ty.ToString(),
        }))
        {
            SetFlash("Écriture config.ini refusée");
            return;
        }

        PanelIpc.SendPanelCmd(_panelDataDir, $"pos {tx} {ty}");
        SetFlash(label);
    }

    private void LockToggle_Toggled(object sender, RoutedEventArgs e)
    {
        if (_suppressOptionEvents) return;
        bool want = LockToggle.IsOn;
        IniConfig.PatchSection(_panelIniPath, "panel", new Dictionary<string, string>
        {
            ["locked"] = want ? "true" : "false",
        });
        PanelIpc.SendPanelCmd(_panelDataDir, $"lock {(want ? 1 : 0)}");
        SetFlash(want ? "Moniteur verrouillé" : "Moniteur déverrouillé (déplaçable à la souris)");
    }

    private void TopmostToggle_Toggled(object sender, RoutedEventArgs e)
    {
        if (_suppressOptionEvents) return;
        bool want = TopmostToggle.IsOn;
        IniConfig.PatchSection(_panelIniPath, "panel", new Dictionary<string, string>
        {
            ["topmost"] = want ? "true" : "false",
        });
        PanelIpc.SendPanelCmd(_panelDataDir, $"topmost {(want ? 1 : 0)}");
        SetFlash(want ? "Moniteur toujours au premier plan" : "Moniteur en mode normal");
    }

    private async void InstallPawnIoBtn_Click(object sender, RoutedEventArgs e)
    {
        InstallPawnIoBtn.IsEnabled = false;
        PawnIoStatusText.Text = "Installation en cours…";
        bool ok = await Task.Run(() => PawnIoHelper.EnsureInstalled(Path.Combine(_panelDir, "libs")));
        InstallPawnIoBtn.IsEnabled = true;
        RefreshOptionsState();
        SetFlash(ok ? "PawnIO installé avec succès" : "Installation PawnIO annulée ou échouée");
    }

    private void RootGrid_KeyDown(object sender, KeyRoutedEventArgs e)
    {
        if (e.Key == VirtualKey.Escape)
        {
            if (OptionsOverlay.Visibility == Visibility.Visible)
            {
                CloseOptionsBtn_Click(sender, e);
                e.Handled = true;
            }
            return;
        }

        if (OptionsOverlay.Visibility == Visibility.Visible || _visibleThemes.Count == 0)
            return;

        if (e.Key == VirtualKey.Enter)
        {
            SoundHelper.PlayClickDown();
            ApplyBtn_Click(sender, e);
            e.Handled = true;
            return;
        }

        int curIdx = _visibleThemes.FindIndex(t => t.Key.Equals(_selectedThemeKey, StringComparison.OrdinalIgnoreCase));
        if (curIdx < 0) curIdx = 0;

        int next = e.Key switch
        {
            VirtualKey.Right => Math.Min(_visibleThemes.Count - 1, curIdx + 1),
            VirtualKey.Left => Math.Max(0, curIdx - 1),
            VirtualKey.Down => Math.Min(_visibleThemes.Count - 1, curIdx + 3),
            VirtualKey.Up => Math.Max(0, curIdx - 3),
            _ => -1,
        };

        if (next >= 0 && next != curIdx)
        {
            _selectedThemeKey = _visibleThemes[next].Key;
            UpdateThemeCardHighlights();
            e.Handled = true;
        }
    }

    private void SetFlash(string text, bool clearLater = true)
    {
        FlashText.Text = text;
        _flashClearTimer.Stop();
        if (clearLater)
            _flashClearTimer.Start();
    }

    private void MainWindow_Closed(object sender, WindowEventArgs args)
    {
        _statusTimer.Stop();
        _brightTimer.Stop();
        _flashClearTimer.Stop();
        SoundHelper.Shutdown();

        // Restaure le dernier thème appliqué si une prévisualisation était en cours
        if (_previewThemeKey is not null && PanelIpc.IsPanelRunning())
            PanelIpc.SendThemeCmd(_panelDataDir, _savedThemeKey);

        // Sauvegarde la position et l'apparence dans centre.ini
        try
        {
            var hwnd = WindowNative.GetWindowHandle(this);
            var appWin = AppWindow.GetFromWindowId(Win32Interop.GetWindowIdFromWindow(hwnd));
            IniConfig.PatchSection(_centreIniPath, "centre", new Dictionary<string, string>
            {
                ["x"] = appWin.Position.X.ToString(),
                ["y"] = appWin.Position.Y.ToString(),
                ["appearance"] = _isDark ? "dark" : "light",
            });
        }
        catch { }
    }
}
