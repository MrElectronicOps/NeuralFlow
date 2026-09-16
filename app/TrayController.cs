using Forms = System.Windows.Forms;
namespace NeuralFlow;
public sealed class TrayController : IDisposable
{
    readonly Forms.NotifyIcon icon;
    readonly Forms.ToolStripMenuItem toggle;
    readonly Forms.ContextMenuStrip menu = new();
    public TrayController(MainWindow window)
    {
        toggle = new Forms.ToolStripMenuItem("Turn effects ON · F8");
        toggle.Click += async (_, _) => await window.Toggle(); menu.Items.Add(toggle);
        menu.Items.Add("Restore original · F9", null, async (_, _) => await window.Stop());
        menu.Items.Add(new Forms.ToolStripSeparator());
        menu.Items.Add("Floating controls", null, (_, _) => window.ShowFloatingControls());
        menu.Items.Add("Open NeuralFlow", null, (_, _) => window.RestoreMainWindow());
        menu.Items.Add("Exit NeuralFlow", null, (_, _) => window.Close());
        icon = new Forms.NotifyIcon { Icon = System.Drawing.Icon.ExtractAssociatedIcon(Environment.ProcessPath!), Text = "NeuralFlow · effects OFF", ContextMenuStrip = menu, Visible = true };
        icon.MouseClick += async (_, e) => { if(e.Button == Forms.MouseButtons.Left) await window.Toggle(); };
    }
    public void Update(bool enabled) { toggle.Text=enabled?"Turn effects OFF · F8":"Turn effects ON · F8"; icon.Text=enabled?"NeuralFlow · effects ON":"NeuralFlow · effects OFF"; toggle.Checked=enabled; }
    public void Dispose() { icon.Visible=false; icon.Icon?.Dispose(); icon.Dispose(); menu.Dispose(); }
}
