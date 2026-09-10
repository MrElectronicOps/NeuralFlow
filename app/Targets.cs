using System.Runtime.InteropServices;
using System.Text;

namespace NeuralFlow;
public record Target(string Name,long Handle,string Kind){public override string ToString()=>Name;}
public record Adapter(string Name,string Luid){public override string ToString()=>Name;}
internal static class Targets
{
    public delegate bool EnumWindow(nint hwnd,nint data);
    public delegate bool EnumMonitor(nint monitor,nint dc,nint rect,nint data);
    [DllImport("user32.dll")]static extern bool EnumWindows(EnumWindow callback,nint data);
    [DllImport("user32.dll")]static extern bool IsWindowVisible(nint hwnd);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)]static extern int GetWindowText(nint hwnd,StringBuilder text,int max);
    [DllImport("user32.dll")]static extern uint GetWindowThreadProcessId(nint hwnd,out uint process);
    [DllImport("user32.dll")]static extern bool EnumDisplayMonitors(nint dc,nint clip,EnumMonitor callback,nint data);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)]static extern bool GetMonitorInfo(nint monitor,ref MonitorInfo info);
    [DllImport("user32.dll")]public static extern short GetAsyncKeyState(int key);
    [DllImport("user32.dll",SetLastError=true)]public static extern bool RegisterHotKey(nint hwnd,int id,uint modifiers,uint key);
    [DllImport("user32.dll")]public static extern bool UnregisterHotKey(nint hwnd,int id);
    [DllImport("user32.dll")]public static extern bool SetWindowDisplayAffinity(nint hwnd,uint affinity);
    [StructLayout(LayoutKind.Sequential)]public struct Rect{public int Left,Top,Right,Bottom;}
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)]struct MonitorInfo{public int Size;public Rect Monitor,Work;public uint Flags;[MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)]public string Device;}
    public static List<Target> Windows(){var list=new List<Target>();EnumWindows((hwnd,_)=>{GetWindowThreadProcessId(hwnd,out uint pid);var name=new StringBuilder(512);GetWindowText(hwnd,name,name.Capacity);if(IsWindowVisible(hwnd)&&pid!=Environment.ProcessId&&name.Length>0&&!name.ToString().StartsWith("NeuralFlow"))list.Add(new Target(name.ToString(),hwnd,"window"));return true;},0);return list.OrderBy(t=>t.Name).ToList();}
    public static List<Target> Monitors(){var list=new List<Target>();EnumDisplayMonitors(0,0,(monitor,_,__,___)=>{var info=new MonitorInfo{Size=Marshal.SizeOf<MonitorInfo>(),Device=""};if(GetMonitorInfo(monitor,ref info))list.Add(new Target($"Display {list.Count+1} · {info.Monitor.Right-info.Monitor.Left} × {info.Monitor.Bottom-info.Monitor.Top}"+((info.Flags&1)!=0?" · primary":""),monitor,"monitor"));return true;},0);return list;}
}
