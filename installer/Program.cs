using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Microsoft.Win32;

namespace NeuralFlow.Setup;
class Program
{
    [STAThread]static void Main(string[] args){if(args.Length==2&&args[0]=="--verify-payload"){SetupWindow.VerifyPayload(args[1]);return;}var app=new Application();app.Run(new SetupWindow(args.Contains("--uninstall")));}
}
class SetupWindow:Window
{
    static string ProductVersion()
    {
        using var payload=Assembly.GetExecutingAssembly().GetManifestResourceStream("NeuralFlow.Payload.zip")??throw new IOException("Installer payload missing.");
        using var zip=new ZipArchive(payload,ZipArchiveMode.Read);
        var entry=zip.Entries.Single(e=>e.FullName is "NeuralFlow-Public/product.json" or "NeuralFlow/product.json");
        using var stream=entry.Open();using var metadata=System.Text.Json.JsonDocument.Parse(stream);
        string version=metadata.RootElement.GetProperty("version").GetString()??throw new IOException("Product version missing.");
        if(string.IsNullOrWhiteSpace(version)||version.IndexOfAny(Path.GetInvalidFileNameChars())>=0||version.Contains(".."))throw new IOException("Invalid product version.");
        return version;
    }
    public static void VerifyPayload(string report)
    {
        using var payload=Assembly.GetExecutingAssembly().GetManifestResourceStream("NeuralFlow.Payload.zip")??throw new IOException("Installer payload missing.");
        using var zip=new ZipArchive(payload,ZipArchiveMode.Read);var files=zip.Entries.Select(e=>e.FullName).ToList();
        if(!files.Any(p=>p.EndsWith("/NeuralFlow.exe"))||!files.Any(p=>p.EndsWith("/engine/service.py"))||!files.Any(p=>p.EndsWith("/python/python.exe")))throw new IOException("Incomplete installer payload.");
        foreach(var entry in zip.Entries){if(entry.FullName.Contains("..")||Path.IsPathRooted(entry.FullName))throw new IOException("Unsafe archive path.");using var input=entry.Open();input.CopyTo(Stream.Null);}
        File.WriteAllText(report,System.Text.Json.JsonSerializer.Serialize(new{verified=true,version=ProductVersion(),files=files.Count,bytes=zip.Entries.Sum(e=>e.Length),nvidia_dll_bundled=files.Any(p=>p.EndsWith("nvngx_dlssnr.dll")),video_codec_bundled=files.Any(p=>p.EndsWith("ffmpeg.exe"))}));
    }
    readonly string basePath=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","NeuralFlow");
    readonly TextBlock status=new(){TextWrapping=TextWrapping.Wrap,Foreground=Brushes.LightGray,Margin=new Thickness(0,20,0,20)};
    readonly Button action=new(){Content="Install NeuralFlow",Padding=new Thickness(22,12,22,12),FontSize=17};
    readonly CheckBox shortcut=new(){Content="Add a desktop shortcut",IsChecked=true,Foreground=Brushes.White,Margin=new Thickness(0,16,0,0)};
    bool working;
    public SetupWindow(bool uninstall)
    {
        Title=uninstall?"Remove NeuralFlow":"NeuralFlow Preview Setup";Width=600;Height=410;ResizeMode=ResizeMode.NoResize;WindowStartupLocation=WindowStartupLocation.CenterScreen;Background=new SolidColorBrush(Color.FromRgb(11,15,23));Foreground=Brushes.White;FontFamily=new FontFamily("Segoe UI");
        var panel=new StackPanel{Margin=new Thickness(32)};Content=panel;
        panel.Children.Add(new TextBlock{Text="NeuralFlow",FontSize=32,FontWeight=FontWeights.SemiBold,Foreground=Brushes.LightCyan});
        panel.Children.Add(new TextBlock{Text="Experimental DLSS 5 Screen Lab",FontSize=15,Foreground=Brushes.LightGray,Margin=new Thickness(0,8,0,0)});
        status.Text=uninstall?"Remove the installed application. Your imported runtime, settings, and rendered videos are preserved.":"Install for your Windows account. No administrator access is needed.\n\nOpen System → Complete setup after installation to verify components and test your GPU. Offline packages use their included components.";
        panel.Children.Add(status);if(!uninstall)panel.Children.Add(shortcut);panel.Children.Add(action);
        action.Content=uninstall?"Remove application":"Install NeuralFlow";
        action.Click+=async(_,__)=>{if(working)return;working=true;action.IsEnabled=false;try{if(uninstall)await Task.Run(Uninstall);else await Task.Run(()=>Install(shortcut.Dispatcher.Invoke(()=>shortcut.IsChecked==true)));status.Text=uninstall?"NeuralFlow application removed. Your settings and videos are preserved.":"Installed. Open NeuralFlow → System → Complete setup. No manual DLL selection is needed.";action.Content="Close";action.IsEnabled=true;action.Click+=(_,__)=>Close();}catch(Exception e){status.Text=e.Message;action.IsEnabled=true;working=false;}};
        Closing+=(_,e)=>{if(working&&!action.IsEnabled)e.Cancel=true;};
    }
    void Install(bool desktop)
    {
        string version=ProductVersion(),destination=Path.Combine(basePath,version);
        if(Process.GetProcessesByName("NeuralFlow").Length>0)throw new IOException("Close NeuralFlow before installing an update.");
        Directory.CreateDirectory(destination);
        using var payload=Assembly.GetExecutingAssembly().GetManifestResourceStream("NeuralFlow.Payload.zip")??throw new IOException("Installer payload is missing.");
        using var zip=new ZipArchive(payload,ZipArchiveMode.Read);
        var manifest=new List<string>();string boundary=Path.GetFullPath(destination)+Path.DirectorySeparatorChar;
        foreach(var entry in zip.Entries){string relative=entry.FullName.Replace('/',Path.DirectorySeparatorChar);foreach(var prefix in new[]{"NeuralFlow-Public","NeuralFlow"})if(relative.StartsWith(prefix+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)){relative=relative[(prefix.Length+1)..];break;}if(string.IsNullOrWhiteSpace(relative))continue;string target=Path.GetFullPath(Path.Combine(destination,relative));if(!target.StartsWith(boundary,StringComparison.OrdinalIgnoreCase))throw new IOException("Invalid installer path.");if(entry.Name.Length==0){Directory.CreateDirectory(target);continue;}Directory.CreateDirectory(Path.GetDirectoryName(target)!);entry.ExtractToFile(target,true);manifest.Add(relative);}
        if(!File.Exists(Path.Combine(destination,"NeuralFlow.exe")))throw new IOException("The installer did not contain the main application.");
        File.WriteAllLines(Path.Combine(destination,"installed-files.txt"),manifest);
        File.WriteAllText(Path.Combine(basePath,"current.txt"),version);
        string setup=Environment.ProcessPath??throw new IOException("Setup path unavailable.");string uninstall=Path.Combine(basePath,"Uninstall.exe");if(!string.Equals(setup,uninstall,StringComparison.OrdinalIgnoreCase))File.Copy(setup,uninstall,true);
        if(desktop)CreateShortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),"NeuralFlow.lnk"),Path.Combine(destination,"NeuralFlow.exe"));
        string programs=Environment.GetFolderPath(Environment.SpecialFolder.Programs);CreateShortcut(Path.Combine(programs,"NeuralFlow.lnk"),Path.Combine(destination,"NeuralFlow.exe"));
        using var key=Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\NeuralFlow");key.SetValue("DisplayName","NeuralFlow Preview");key.SetValue("DisplayVersion",version);key.SetValue("InstallLocation",destination);key.SetValue("UninstallString","\""+uninstall+"\" --uninstall");key.SetValue("NoModify",1);key.SetValue("NoRepair",1);
    }
    static void CreateShortcut(string path,string target){Type shell=Type.GetTypeFromProgID("WScript.Shell")!;dynamic obj=Activator.CreateInstance(shell)!;dynamic link=obj.CreateShortcut(path);link.TargetPath=target;link.WorkingDirectory=Path.GetDirectoryName(target);link.Description="NeuralFlow — Experimental DLSS 5 Screen Lab";link.Save();}
    void Uninstall()
    {
        if(Process.GetProcessesByName("NeuralFlow").Length>0)throw new IOException("Close NeuralFlow before removing it.");
        string current=Path.Combine(basePath,"current.txt");if(!File.Exists(current))throw new IOException("No installed version was found.");string version=File.ReadAllText(current).Trim();if(version.IndexOfAny(Path.GetInvalidFileNameChars())>=0||version.Contains("..")||version.Contains(Path.DirectorySeparatorChar))throw new IOException("Invalid install manifest.");string destination=Path.GetFullPath(Path.Combine(basePath,version));string boundary=destination+Path.DirectorySeparatorChar;
        foreach(string relative in File.ReadAllLines(Path.Combine(destination,"installed-files.txt"))){string target=Path.GetFullPath(Path.Combine(destination,relative));if(!target.StartsWith(boundary,StringComparison.OrdinalIgnoreCase))throw new IOException("Invalid uninstall path.");if(File.Exists(target))File.Delete(target);}
        File.Delete(Path.Combine(destination,"installed-files.txt"));foreach(string folder in Directory.GetDirectories(destination,"*",SearchOption.AllDirectories).OrderByDescending(s=>s.Length))if(!Directory.EnumerateFileSystemEntries(folder).Any())Directory.Delete(folder);if(!Directory.EnumerateFileSystemEntries(destination).Any())Directory.Delete(destination);File.Delete(current);
        foreach(string folder in new[]{Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),Environment.GetFolderPath(Environment.SpecialFolder.Programs)}){string link=Path.Combine(folder,"NeuralFlow.lnk");if(File.Exists(link))File.Delete(link);}
        Registry.CurrentUser.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\NeuralFlow",false);
    }
}
