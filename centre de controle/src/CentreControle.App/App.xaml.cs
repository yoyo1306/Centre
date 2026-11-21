using CentreControle.Core;
using Microsoft.UI.Xaml;

namespace CentreControle.App;

public partial class App : Application
{
    private static Mutex? _singleInstanceMutex;
    private MainWindow? _window;

    public App()
    {
        InitializeComponent();
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        _singleInstanceMutex = new Mutex(true, "CentreControleSingleInstance", out bool createdNew);
        if (!createdNew)
        {
            PanelIpc.FocusExistingWindow("Centre de contrôle");
            Exit();
            return;
        }

        _window = new MainWindow();
        _window.Activate();
    }
}
