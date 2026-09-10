using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Threading;
using Microsoft.Win32;

namespace NeuralFlow;
public partial class MainWindow : Window
{
    readonly EngineClient engine=new();
    readonly DispatcherTimer settingsTimer=new(){Interval=TimeSpan.FromMilliseconds(250)};
    readonly DispatcherTimer heartbeat=new(){Interval=TimeSpan.FromMilliseconds(150)};
    bool ready,enabled,busy,loading,closing,monitorMode,playing,showOriginal,updatingSeek,fullscreen;
    bool f8Registered,f9Registered;
    bool starting;
    bool setupRunning;
    long liveGeneration;
    HwndSource? hotkeySource;
    string preset="Balanced",sourcePath="",outputPath="",diagnostics="";
    FloatingWindow? floating;
    Window? playerWindow;
    JsonElement lastStatus;
    public Slider StrengthControl=>Strength;
    public Slider StabilityControl=>Stability;
    public TextBlock StatusControl=>Status;
    public MainWindow()
    {
        InitializeComponent();
        SourceInitialized+=(_,__)=>{
            var handle=new WindowInteropHelper(this).Handle;
            hotkeySource=HwndSource.FromHwnd(handle);hotkeySource?.AddHook(HotkeyMessage);
            f8Registered=Targets.RegisterHotKey(handle,8,0x4000,0x77);
            f9Registered=Targets.RegisterHotKey(handle,9,0x4000,0x78);
        };
        PreviewKeyDown+=async(_,e)=>{
            if(e.IsRepeat)return;
            if(!f8Registered&&e.Key==System.Windows.Input.Key.F8){e.Handled=true;await Toggle();}
            if(!f9Registered&&e.Key==System.Windows.Input.Key.F9){e.Handled=true;await Stop();}
        };
        settingsTimer.Tick+=async(_,__)=>{settingsTimer.Stop();SaveSettings();if(ready&&enabled)await Execute(async()=>await engine.Send("settings",new{settings=Settings()}));};
        heartbeat.Tick+=async(_,__)=>{
            if(playing&&!updatingSeek){updatingSeek=true;Seek.Value=EnhancedPlayer.Position.TotalSeconds;updatingSeek=false;
                if(Math.Abs((OriginalPlayer.Position-EnhancedPlayer.Position).TotalSeconds)>.12)OriginalPlayer.Position=EnhancedPlayer.Position;
            }
        };
        engine.Event+=data=>Dispatcher.BeginInvoke(()=>OnEvent(data));
        engine.Failed+=message=>Dispatcher.BeginInvoke(()=>{if(!closing){ready=false;SetEnabled(false);Status.Text=message;}});
        Loaded+=async(_,__)=>{
            LoadBrand();LoadSettings();RefreshTargets();ShowPage("Live");ApplyLayout();
            if(!Targets.SetWindowDisplayAffinity(new WindowInteropHelper(this).Handle,0x11))Status.Text="Control-window capture exclusion was unavailable.";
            await Execute(async()=>{await engine.Start();ready=true;await engine.Send("exclude",new{hwnd=new WindowInteropHelper(this).Handle.ToInt64()});ApplyStatus(await engine.Send("status"));Status.Text="Ready · effects OFF · F9 restores original";});
            if(!f8Registered||!f9Registered)Status.Text="Effects OFF · a shortcut is in use by another app. Use the on-screen controls.";
            heartbeat.Start();
            var args=Environment.GetCommandLineArgs();int qa=Array.IndexOf(args,"--ui-checks");
            if(qa>=0&&args.Length>qa+1)await RunUiChecks(args[qa+1]);
            int playback=Array.IndexOf(args,"--playback-checks");
            if(playback>=0&&args.Length>playback+3)await RunPlaybackChecks(args[playback+1],args[playback+2],args[playback+3]);
            int control=Array.IndexOf(args,"--control-checks");
            if(control>=0&&args.Length>control+1)await RunControlChecks(args[control+1]);
            int setupCheck=Array.IndexOf(args,"--setup-checks");
            if(setupCheck>=0&&args.Length>setupCheck+1)await RunSetupChecks(args[setupCheck+1]);
        };
        Closing+=(_,e)=>{
            if(closing)return;
            if(busy&&MessageBox.Show("Cancel the current preparation and close NeuralFlow?","NeuralFlow",MessageBoxButton.YesNo)!=MessageBoxResult.Yes){e.Cancel=true;return;}
            closing=true;heartbeat.Stop();settingsTimer.Stop();
            var handle=new WindowInteropHelper(this).Handle;
            if(f8Registered)Targets.UnregisterHotKey(handle,8);if(f9Registered)Targets.UnregisterHotKey(handle,9);
            hotkeySource?.RemoveHook(HotkeyMessage);
            SaveSettings();OriginalPlayer.Close();EnhancedPlayer.Close();floating?.Close();playerWindow?.Close();engine.Dispose();
        };
    }
    nint HotkeyMessage(nint hwnd,int message,nint id,nint data,ref bool handled)
    {
        if(message==0x0312&&(id==8||id==9)){
            handled=true;
            Dispatcher.BeginInvoke(async()=>{if(closing)return;if(id==9)await Stop();else await Toggle();});
        }
        return 0;
    }
    async Task Execute(Func<Task> action){try{await action();}catch(Exception e){Status.Text=e.Message;}}
    object Settings()=>new{strength=Strength.Value/100,stability=Stability.Value/100,size=Combo(Resolution),refresh=int.Parse(Combo(RefreshRate)),clarity=Clarity.Value/100,saturation=Vibrance.Value/100,contrast=Contrast.Value/100,brightness=Brightness.Value/100,warmth=Warmth.Value/100,tone=Tone.Value/100,preset};
    static string Combo(ComboBox box)=>box.SelectedItem is ComboBoxItem item?item.Content?.ToString()??"Auto":box.SelectedItem?.ToString()??"Auto";
    public async Task Toggle(){if(enabled||starting){await Stop();return;}if(!ready){Status.Text="The local engine is not ready. Check System for details.";return;}if(busy){Status.Text="Finish or cancel video preparation before enabling live effects.";return;}if(TargetPicker.SelectedItem is not Target target){Status.Text="Choose an application window or display first.";return;}
        long generation=++liveGeneration;starting=true;Status.Text="Starting enhancement · F9 cancels";
        try{
            await engine.Send("start",new{target=target.Handle,kind=target.Kind,settings=Settings()});
            if(closing||generation!=liveGeneration)return;
            SetEnabled(true);Status.Text="Enhancing · return to your chosen window · F9 restores original";
        }catch(Exception e){if(generation==liveGeneration){SetEnabled(false);Status.Text=e.Message;}}
        finally{if(generation==liveGeneration)starting=false;}
    }
    public async Task Stop(){long generation=++liveGeneration;starting=false;SetEnabled(false);if(ready)await Execute(async()=>await engine.Send("stop"));if(generation==liveGeneration)Status.Text="Effects OFF · original picture restored";}
    public async Task Compare(bool hold){if(ready&&enabled)await Execute(async()=>await engine.Send("compare",new{hold}));}
    void SetEnabled(bool value){enabled=value;EnableButton.Content=value?"Effects on · F8":"Enable effects · F8";EffectState.Text=value?"Your picture, enhanced":"Ready when you are";EffectDescription.Text=value?"Live enhancement · compare with F8 or the floating controls.":"Effects are off. Original picture is visible.";}
    void SettingsChanged(object sender,RoutedEventArgs e){if(!IsLoaded||loading)return;settingsTimer.Stop();settingsTimer.Start();}
    void RefreshTargets(){var previous=TargetPicker.SelectedItem as Target;TargetPicker.ItemsSource=monitorMode?Targets.Monitors():Targets.Windows();if(previous is not null)TargetPicker.SelectedItem=((IEnumerable<Target>)TargetPicker.ItemsSource).FirstOrDefault(t=>t.Handle==previous.Handle);if(monitorMode&&TargetPicker.SelectedItem is null&&TargetPicker.Items.Count>0)TargetPicker.SelectedIndex=0;
        WindowMode.BorderBrush=monitorMode?new SolidColorBrush(Color.FromRgb(52,67,91)):(Brush)FindResource("AccentBrush");MonitorMode.BorderBrush=monitorMode?(Brush)FindResource("AccentBrush"):new SolidColorBrush(Color.FromRgb(52,67,91));TargetHint.Text=monitorMode?"The entire selected display is enhanced. Protected or HDR content may be unavailable.":"Choose a window, then enable and return to it. Your controls stay available.";}
    async void TargetChanged(object sender,SelectionChangedEventArgs e){if(enabled||starting)await Stop();}
    async void WindowModeClick(object sender,RoutedEventArgs e){await Stop();monitorMode=false;RefreshTargets();}
    async void MonitorModeClick(object sender,RoutedEventArgs e){await Stop();monitorMode=true;RefreshTargets();}
    void RefreshClick(object sender,RoutedEventArgs e)=>RefreshTargets();
    async void EnableClick(object sender,RoutedEventArgs e)=>await Toggle();
    async void StopClick(object sender,RoutedEventArgs e)=>await Stop();
    void LiveClick(object sender,RoutedEventArgs e)=>ShowPage("Live");
    void VideoClick(object sender,RoutedEventArgs e)=>ShowPage("Video");
    void SystemClick(object sender,RoutedEventArgs e)=>ShowPage("System");
    void ShowPage(string page){LivePage.Visibility=page=="Live"?Visibility.Visible:Visibility.Collapsed;VideoPage.Visibility=page=="Video"?Visibility.Visible:Visibility.Collapsed;SystemPage.Visibility=page=="System"?Visibility.Visible:Visibility.Collapsed;PageScroller.ScrollToTop();foreach(var pair in new[]{(LiveNav,"Live"),(VideoNav,"Video"),(SystemNav,"System")})pair.Item1.Background=new SolidColorBrush(pair.Item2==page?Color.FromRgb(35,58,72):Color.FromRgb(20,29,43));}
    void OnSizeChanged(object sender,SizeChangedEventArgs e){ApplyLayout();if(LiveNav is null)return;bool compact=ActualWidth<760;foreach(var button in new[]{LiveNav,VideoNav,SystemNav})button.Padding=new Thickness(compact?0:18,11,compact?0:18,11);LiveNav.ToolTip="Live enhancement";VideoNav.ToolTip="Video Studio";SystemNav.ToolTip="System";}
    void ApplyLayout(){if(ControlGrid is null)return;bool wide=ActualWidth>=1100;Grid.SetColumn(ColorCard,wide?1:0);Grid.SetRow(ColorCard,wide?0:1);Grid.SetColumnSpan(NeuralCard,wide?1:2);Grid.SetColumnSpan(ColorCard,wide?1:2);NeuralCard.Margin=new Thickness(0,0,wide?8:0,16);ColorCard.Margin=new Thickness(wide?8:0,0,0,16);bool compact=ActualWidth<760;NavColumn.Width=new GridLength(compact?64:176);LiveNav.Content=compact?"◉":"◉   Live";VideoNav.Content=compact?"▷":"▷   Video Studio";SystemNav.Content=compact?"⚙":"⚙   System";VersionLabel.Visibility=compact?Visibility.Collapsed:Visibility.Visible;Descriptor.Visibility=ActualWidth<1060?Visibility.Collapsed:Visibility.Visible;PageScroller.Padding=new Thickness(compact?16:28,24,compact?16:28,24);}
    void PresetClick(object sender,RoutedEventArgs e){preset=(string)((Button)sender).Tag;loading=true;Strength.Value=preset=="Smooth"?10:preset=="Detail"?35:15;Stability.Value=preset=="Detail"?65:75;RefreshRate.SelectedIndex=preset=="Smooth"?1:2;Resolution.SelectedIndex=0;Clarity.Value=Vibrance.Value=Contrast.Value=Brightness.Value=Warmth.Value=Tone.Value=0;loading=false;SettingsChanged(this,e);Status.Text=preset+" preset selected";}
    async void FloatingClick(object sender,RoutedEventArgs e){if(floating is not null){floating.Activate();return;}floating=new FloatingWindow(this);floating.Closed+=(_,__)=>floating=null;floating.Show();Targets.SetWindowDisplayAffinity(new WindowInteropHelper(floating).Handle,0x11);if(ready)await Execute(async()=>await engine.Send("exclude",new{hwnd=new WindowInteropHelper(floating).Handle.ToInt64()}));}
    void LoadBrand(){try{var data=JsonDocument.Parse(File.ReadAllText(Path.Combine(Paths.Root,"product.json"))).RootElement;Title=data.GetProperty("name").GetString();Brand.Text=Title;Descriptor.Text=data.GetProperty("descriptor").GetString()?.ToUpperInvariant();AboutText.Text=data.GetProperty("about").GetString();VersionLabel.Text="PREVIEW "+data.GetProperty("version").GetString()+"\nLOCAL PROCESSING";}catch{AboutText.Text="NeuralFlow is an independent experimental project, not affiliated with NVIDIA.";}}
    void SaveSettings(){if(!IsLoaded)return;try{Directory.CreateDirectory(Paths.Data);File.WriteAllText(Path.Combine(Paths.Data,"appearance.json"),JsonSerializer.Serialize(Settings(),new JsonSerializerOptions{WriteIndented=true}));}catch{}}
    void LoadSettings(){try{loading=true;var s=JsonDocument.Parse(File.ReadAllText(Path.Combine(Paths.Data,"appearance.json"))).RootElement;foreach(var pair in new[]{("strength",Strength),("stability",Stability),("clarity",Clarity),("saturation",Vibrance),("contrast",Contrast),("brightness",Brightness),("warmth",Warmth),("tone",Tone)})if(s.TryGetProperty(pair.Item1,out var value))pair.Item2.Value=value.GetDouble()*100;if(s.TryGetProperty("refresh",out var r))RefreshRate.SelectedIndex=Math.Clamp(r.GetInt32()-1,0,3);if(s.TryGetProperty("preset",out var p))preset=p.GetString()??"Balanced";}catch{}finally{loading=false;}}
    void ApplyStatus(JsonElement data){lastStatus=data.Clone();diagnostics=JsonSerializer.Serialize(data,new JsonSerializerOptions{WriteIndented=true});Diagnostics.Text=diagnostics;var b=data.TryGetProperty("backend",out var backend)?backend:data;
        bool neuralReady=b.TryGetProperty("supported_sizes",out var supported)&&supported.GetArrayLength()>0;
        bool mediaReady=data.TryGetProperty("media",out var setupMedia)&&setupMedia.TryGetProperty("available",out var mediaAvailable)&&mediaAvailable.GetBoolean();
        SetupBanner.Visibility=neuralReady&&mediaReady?Visibility.Collapsed:Visibility.Visible;
        if(!setupRunning)SetupStatus.Text=neuralReady&&mediaReady?"Ready. Neural components, video tools and hardware checks are complete.":"Click Complete setup. We download the files and check compatibility for you.";
        if(data.TryGetProperty("media",out var media)){bool available=media.TryGetProperty("available",out var a)&&a.GetBoolean();MediaToolsStatus.Text=available?"Video tools are ready for local rendering.":"Download video tools to enable Video Studio.";InstallMediaButton.IsEnabled=!available&&!busy;}
        loading=true;try{var adapters=new List<Adapter>();if(b.TryGetProperty("adapters",out var aa))foreach(var a in aa.EnumerateArray())if(a.GetProperty("vendor_id").GetInt32()==0x10de)adapters.Add(new Adapter(a.TryGetProperty("name",out var n)?n.GetString()??"NVIDIA GPU":a.GetProperty("description").GetString()??"NVIDIA GPU",a.GetProperty("luid").GetString()??""));AdapterPicker.ItemsSource=adapters;if(b.TryGetProperty("adapter",out var current)&&current.ValueKind==JsonValueKind.Object)AdapterPicker.SelectedItem=adapters.FirstOrDefault(a=>a.Luid==current.GetProperty("luid").GetString());
        string name=(AdapterPicker.SelectedItem as Adapter)?.Name??"No NVIDIA adapter selected";string state=b.TryGetProperty("compatibility",out var comp)?comp.GetString()??"Not tested":"Not tested";HardwareSummary.Text=name+"\n"+state;if(b.TryGetProperty("error",out var error)&&error.ValueKind==JsonValueKind.String)HardwareSummary.Text+="\n"+error.GetString();
        string old=Combo(Resolution);Resolution.Items.Clear();Resolution.Items.Add("Auto");if(b.TryGetProperty("supported_sizes",out var sizes))foreach(var size in sizes.EnumerateArray())Resolution.Items.Add(size.GetInt32().ToString());Resolution.SelectedItem=Resolution.Items.Contains(old)?old:"Auto";
        }finally{loading=false;}}
    async void ImportClick(object sender,RoutedEventArgs e){if(busy)return;var dialog=new OpenFolderDialog{Title="Select the folder containing nvngx_dlssnr.dll and caller/nvngx.dll_comfy.dll"};if(dialog.ShowDialog()!=true)return;await Stop();await Execute(async()=>{await engine.Send("import_runtime",new{path=dialog.FolderName});ApplyStatus(await engine.Send("status"));Status.Text="Runtime imported and verified. Run Check my hardware next.";});}
    async void AdapterChanged(object sender,SelectionChangedEventArgs e){if(!ready||loading||busy||AdapterPicker.SelectedItem is not Adapter adapter)return;await Stop();await Execute(async()=>{await engine.Send("adapter",new{luid=adapter.Luid});ApplyStatus(await engine.Send("status"));});}
    async void BenchmarkClick(object sender,RoutedEventArgs e){if(!ready||busy)return;await Stop();await Execute(async()=>{await engine.Send("benchmark");SetBusy(true);BenchmarkStatus.Text="Checking initialization and neural output at each size…";});}
    async void InstallMediaClick(object sender,RoutedEventArgs e){if(!ready||busy)return;await Stop();await Execute(async()=>{await engine.Send("install_media");SetBusy(true);MediaToolsStatus.Text="Downloading and verifying video tools…";});}
    async void CompleteSetupClick(object sender,RoutedEventArgs e){
        if(!ready||busy)return;await Stop();setupRunning=true;SetBusy(true);
        SetupProgress.Visibility=Visibility.Visible;SetupStatus.Text="Preparing your setup…";
        try{await engine.Send("complete_setup");}catch(Exception error){SetBusy(false);SetupStatus.Text=Status.Text=error.Message;}
    }
    void SetBusy(bool value){busy=value;BenchmarkButton.IsEnabled=RenderButton.IsEnabled=CompleteSetupButton.IsEnabled=!value;AdapterPicker.IsEnabled=!value;if(!value){setupRunning=false;SetupProgress.Visibility=Visibility.Collapsed;}}
    async void CancelClick(object sender,RoutedEventArgs e){if(ready)await Execute(async()=>{await engine.Send("cancel");Status.Text="Cancellation requested; waiting for the current operation to finish.";});}
    void SaveDiagnosticsClick(object sender,RoutedEventArgs e){var dialog=new SaveFileDialog{Filter="JSON report|*.json",FileName="NeuralFlow-diagnostics.json"};if(dialog.ShowDialog()==true)File.WriteAllText(dialog.FileName,diagnostics);}
    async void ResetClick(object sender,RoutedEventArgs e){await Stop();loading=true;Strength.Value=15;Stability.Value=75;Clarity.Value=Vibrance.Value=Contrast.Value=Brightness.Value=Warmth.Value=Tone.Value=0;Resolution.SelectedIndex=0;RefreshRate.SelectedIndex=2;loading=false;SaveSettings();}
    void ChooseVideoClick(object sender,RoutedEventArgs e){if(busy)return;var dialog=new OpenFileDialog{Filter="Videos|*.mp4;*.mkv;*.mov;*.avi;*.webm;*.m4v|All files|*.*"};if(dialog.ShowDialog()==true)SetVideo(dialog.FileName);}
    void VideoDrop(object sender,DragEventArgs e){if(!busy&&e.Data.GetData(DataFormats.FileDrop) is string[] files&&files.Length>0)SetVideo(files[0]);}
    void SetVideo(string path){sourcePath=path;VideoSourceLabel.Text=Path.GetFileName(path);VideoSourceLabel.ToolTip=path;}
    async void RenderClick(object sender,RoutedEventArgs e){if(busy||!ready)return;if(!File.Exists(sourcePath)){RenderStatus.Text="Choose a local video first.";return;}bool mkv=VideoFormat.SelectedIndex==1;var dialog=new SaveFileDialog{Filter=mkv?"Lossless MKV|*.mkv":"High-quality MP4|*.mp4",FileName=Path.GetFileNameWithoutExtension(sourcePath)+"-NeuralFlow"+(mkv?".mkv":".mp4"),OverwritePrompt=true};if(dialog.ShowDialog()!=true)return;if(File.Exists(dialog.FileName)){RenderStatus.Text="Choose a new filename. Existing files are preserved.";return;}
        await Stop();await Execute(async()=>{outputPath=dialog.FileName;await engine.Send("export",new{source=sourcePath,destination=outputPath,strength=VideoStrength.Value/100,stability=VideoStability.Value/100});SetBusy(true);RenderProgress.Value=0;RenderStatus.Text="Preparing source and neural renderer…";});}
    void OnEvent(JsonElement message){if(!message.TryGetProperty("type",out var t))return;string type=t.GetString()??"";var data=message.TryGetProperty("data",out var d)?d:message;
        if(type=="complete"&&data.TryGetProperty("kind",out var setupKind)&&setupKind.GetString()=="setup"){SetBusy(false);ApplyStatus(data);Status.Text=SetupStatus.Text="Setup complete · choose a source in Live · effects are OFF";return;}
        if(type=="complete"&&data.TryGetProperty("kind",out var completed)&&completed.GetString()=="media"){SetBusy(false);MediaToolsStatus.Text="Video tools installed and verified.";Status.Text=MediaToolsStatus.Text;_ = Execute(async()=>ApplyStatus(await engine.Send("status")));return;}
        if(type=="stats"){if(enabled){string text=data.TryGetProperty("message",out var m)?m.GetString()??"Enhancing":"Enhancing";Status.Text=text;if(data.TryGetProperty("active",out var active)&&!active.GetBoolean())SetEnabled(false);}return;}
        if(type=="progress"){string text=data.TryGetProperty("message",out var m)?m.GetString()??"Preparing…":data.ToString();Status.Text=BenchmarkStatus.Text=RenderStatus.Text=text;if(setupRunning)SetupStatus.Text=text;if(data.TryGetProperty("percent",out var p))RenderProgress.Value=p.GetDouble();return;}
        if(type=="complete"){SetBusy(false);Status.Text="Preparation complete";if(data.TryGetProperty("kind",out var k)&&k.GetString()=="benchmark"){BenchmarkStatus.Text="Hardware check complete. Validated sizes are now available.";_ = Execute(async()=>ApplyStatus(await engine.Send("status")));}else if(data.TryGetProperty("original_playback",out var original)&&data.TryGetProperty("enhanced_playback",out var enhanced)){LoadPlayers(original.GetString()!,enhanced.GetString()!);RenderProgress.Value=100;RenderStatus.Text="Render complete and decode-checked.";}return;}
        if(type=="error"||type=="cancelled"){SetBusy(false);string text=data.TryGetProperty("message",out var m)?m.GetString()??type:type;Status.Text=RenderStatus.Text=BenchmarkStatus.Text=SetupStatus.Text=text;if(type=="error")SetEnabled(false);_ = Execute(async()=>{var fresh=await engine.Send("status");ApplyStatus(fresh);SetupStatus.Text=text;});}
    }
    void LoadPlayers(string original,string enhanced){OriginalPlayer.Source=new Uri(original);EnhancedPlayer.Source=new Uri(enhanced);OriginalPlayer.Volume=0;EnhancedPlayer.Volume=Volume.Value;OriginalPlayer.Pause();EnhancedPlayer.Pause();playing=false;showOriginal=false;EnhancedPlayer.Opacity=1;PlayerState.Text="Enhanced · ready to play";CompareVideoButton.Content="Show original";}
    void MediaOpened(object sender,RoutedEventArgs e){if(EnhancedPlayer.NaturalDuration.HasTimeSpan)Seek.Maximum=EnhancedPlayer.NaturalDuration.TimeSpan.TotalSeconds;}
    void MediaEnded(object sender,RoutedEventArgs e){OriginalPlayer.Pause();EnhancedPlayer.Pause();playing=false;}
    void MediaFailed(object sender,ExceptionRoutedEventArgs e){playing=false;PlayerState.Text="Playback failed: "+e.ErrorException.Message;}
    void PlayClick(object sender,RoutedEventArgs e){if(EnhancedPlayer.Source is null)return;if(playing){OriginalPlayer.Pause();EnhancedPlayer.Pause();}else{if(EnhancedPlayer.Position.TotalSeconds>=Seek.Maximum-.1){OriginalPlayer.Position=EnhancedPlayer.Position=TimeSpan.Zero;}OriginalPlayer.Play();EnhancedPlayer.Play();}playing=!playing;}
    void CompareVideoClick(object sender,RoutedEventArgs e){showOriginal=!showOriginal;OriginalPlayer.Position=EnhancedPlayer.Position;EnhancedPlayer.Opacity=showOriginal?0:1;CompareVideoButton.Content=showOriginal?"Show enhanced":"Show original";PlayerState.Text=showOriginal?"Original · audio stays synchronized":"Enhanced · audio stays synchronized";}
    void SeekChanged(object sender,RoutedPropertyChangedEventArgs<double> e){if(!IsLoaded||updatingSeek||EnhancedPlayer.Source is null)return;OriginalPlayer.Position=EnhancedPlayer.Position=TimeSpan.FromSeconds(Seek.Value);}
    void VolumeChanged(object sender,RoutedPropertyChangedEventArgs<double> e){if(EnhancedPlayer is not null)EnhancedPlayer.Volume=e.NewValue;}
    void FullscreenClick(object sender,RoutedEventArgs e){if(fullscreen)return;fullscreen=true;var parent=(Panel)PlayerSurface.Parent;int index=parent.Children.IndexOf(PlayerSurface);parent.Children.Remove(PlayerSurface);PlayerSurface.Height=double.NaN;playerWindow=new Window{Title="NeuralFlow playback",WindowStyle=WindowStyle.None,WindowState=WindowState.Maximized,Background=Brushes.Black,Content=PlayerSurface};playerWindow.KeyDown+=(_,key)=>{if(key.Key==System.Windows.Input.Key.Escape)playerWindow.Close();if(key.Key==System.Windows.Input.Key.Space)PlayClick(this,new());if(key.Key==System.Windows.Input.Key.Tab)CompareVideoClick(this,new());};playerWindow.MouseDoubleClick+=(_,__)=>playerWindow.Close();playerWindow.Closed+=(_,__)=>{playerWindow.Content=null;PlayerSurface.Height=320;parent.Children.Insert(index,PlayerSurface);fullscreen=false;};playerWindow.Show();}
    void OpenOutputClick(object sender,RoutedEventArgs e){if(File.Exists(outputPath))Process.Start(new ProcessStartInfo(outputPath){UseShellExecute=true});}
}
