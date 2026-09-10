using System.IO;
using System.Windows;

namespace NeuralFlow;
public partial class App : Application
{
    private Mutex? mutex;
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        mutex = new Mutex(true, "Local\\NeuralFlow.Preview", out bool created);
        if (!created) { MessageBox.Show("NeuralFlow is already running. Open its existing window.", "NeuralFlow"); Shutdown(); return; }
        DispatcherUnhandledException += (_, error) => {
            Directory.CreateDirectory(Paths.Data);
            File.AppendAllText(Path.Combine(Paths.Data, "ui-errors.log"), error.Exception + Environment.NewLine);
            MessageBox.Show(error.Exception.Message, "NeuralFlow"); error.Handled = true;
        };
        var window = new MainWindow(); MainWindow = window; window.Show();
    }
    protected override void OnExit(ExitEventArgs e) { mutex?.Dispose(); base.OnExit(e); }
}
public static class Paths
{
    public static string Root => AppContext.BaseDirectory;
    public static string Data => Environment.GetEnvironmentVariable("NEURALFLOW_DATA") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "NeuralFlow");
}
