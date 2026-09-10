using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace NeuralFlow;
public partial class MainWindow
{
    async Task RunSetupChecks(string reportPath)
    {
        ShowPage("System");CompleteSetupClick(this,new RoutedEventArgs());
        DateTime deadline=DateTime.UtcNow.AddSeconds(120);
        while(!SetupStatus.Text.StartsWith("Setup complete")&&DateTime.UtcNow<deadline)await Task.Delay(100);
        bool passed=SetupStatus.Text.StartsWith("Setup complete")&&!busy&&!enabled&&CompleteSetupButton.IsEnabled&&SetupBanner.Visibility==Visibility.Collapsed;
        Directory.CreateDirectory(Path.GetDirectoryName(reportPath)!);
        File.WriteAllText(reportPath,JsonSerializer.Serialize(new{passed,status=SetupStatus.Text,button_ready=CompleteSetupButton.IsEnabled,spinner_hidden=SetupProgress.Visibility==Visibility.Collapsed,effects_off=!enabled},new JsonSerializerOptions{WriteIndented=true}));
        await RunUiChecks(Path.Combine(Path.GetDirectoryName(reportPath)!,"setup-ui"));
    }
    async Task RunControlChecks(string reportPath)
    {
        var controls=new[]{Strength,Clarity,Vibrance,Contrast,Brightness,Warmth,Tone};
        var previous=controls.Select(c=>c.Value).ToArray();
        var results=new Dictionary<string,object>();
        try{
            // Capture only this app's excluded control window, with neutral effects.
            // No desktop content is captured and no visible overlay is needed.
            loading=true;Strength.Value=Clarity.Value=Brightness.Value=Warmth.Value=Tone.Value=0;
            Vibrance.Value=Contrast.Value=0;loading=false;
            TargetPicker.ItemsSource=new[]{new Target("NeuralFlow control check",new System.Windows.Interop.WindowInteropHelper(this).Handle.ToInt64(),"window")};
            TargetPicker.SelectedIndex=0;
            async Task VerifyOff(string name){var status=await engine.Send("status");bool off=!enabled&&!starting&&!status.GetProperty("active").GetBoolean();results[name]=off;if(!off)throw new InvalidOperationException(name+" failed to restore original state.");}
            var begin=Toggle();results["first_start_was_pending"]=starting;await Task.WhenAll(begin,Stop());await VerifyOff("stop_during_start");
            begin=Toggle();results["second_start_was_pending"]=starting;await Task.WhenAll(begin,Toggle());await VerifyOff("toggle_during_start");
            await Toggle();results["completed_start"]=enabled;if(!enabled)throw new InvalidOperationException(Status.Text);
            await Stop();await VerifyOff("stop_after_start");results["passed"]=true;
        }catch(Exception e){results["passed"]=false;results["error"]=e.ToString();await Stop();}
        finally{
            loading=true;for(int i=0;i<controls.Length;i++)controls[i].Value=previous[i];loading=false;
            Directory.CreateDirectory(Path.GetDirectoryName(reportPath)!);File.WriteAllText(reportPath,JsonSerializer.Serialize(results,new JsonSerializerOptions{WriteIndented=true}));Close();
        }
    }
    async Task RunPlaybackChecks(string original,string enhanced,string reportPath)
    {
        ShowPage("Video");LoadPlayers(original,enhanced);
        DateTime deadline=DateTime.UtcNow.AddSeconds(15);
        while((!OriginalPlayer.NaturalDuration.HasTimeSpan||!EnhancedPlayer.NaturalDuration.HasTimeSpan)&&DateTime.UtcNow<deadline)await Task.Delay(100);
        if(!OriginalPlayer.NaturalDuration.HasTimeSpan||!EnhancedPlayer.NaturalDuration.HasTimeSpan)throw new InvalidOperationException("Video player did not open both media sources: "+PlayerState.Text);
        PlayClick(this,new RoutedEventArgs());await Task.Delay(650);
        double difference=Math.Abs((OriginalPlayer.Position-EnhancedPlayer.Position).TotalMilliseconds);
        if(EnhancedPlayer.Position.TotalSeconds<=0)throw new InvalidOperationException("Enhanced playback clock did not advance.");
        CompareVideoClick(this,new RoutedEventArgs());await Task.Delay(100);
        bool originalVisible=EnhancedPlayer.Opacity==0;
        CompareVideoClick(this,new RoutedEventArgs());PlayClick(this,new RoutedEventArgs());Seek.Value=.25;await Task.Delay(200);
        var result=new {original_opened=true,enhanced_opened=true,original_width=OriginalPlayer.NaturalVideoWidth,enhanced_width=EnhancedPlayer.NaturalVideoWidth,duration_difference_ms=Math.Abs((OriginalPlayer.NaturalDuration.TimeSpan-EnhancedPlayer.NaturalDuration.TimeSpan).TotalMilliseconds),playback_position_difference_ms=difference,original_toggle_visible=originalVisible,enhanced_toggle_visible=EnhancedPlayer.Opacity==1,original_muted=OriginalPlayer.Volume==0,seek_seconds=EnhancedPlayer.Position.TotalSeconds};
        Directory.CreateDirectory(Path.GetDirectoryName(reportPath)!);File.WriteAllText(reportPath,JsonSerializer.Serialize(result,new JsonSerializerOptions{WriteIndented=true}));
        if(difference>120||!originalVisible)throw new InvalidOperationException("Playback comparison drift exceeded its tolerance.");
        Close();
    }
    async Task RunUiChecks(string folder)
    {
        Directory.CreateDirectory(folder);
        var results=new List<object>();
        foreach(var test in new[]{("live-wide","Live",1240d,900d),("live-compact","Live",700d,800d),("video","Video",1100d,900d),("system","System",1100d,900d)})
        {
            Width=test.Item3;Height=test.Item4;ShowPage(test.Item2);ApplyLayout();
            await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
            UpdateLayout();
            var visual=(FrameworkElement)Content;
            var bitmap=new RenderTargetBitmap((int)Math.Ceiling(visual.ActualWidth),(int)Math.Ceiling(visual.ActualHeight),96,96,PixelFormats.Pbgra32);
            bitmap.Render(visual);var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(bitmap));
            using(var stream=File.Create(Path.Combine(folder,test.Item1+".png")))encoder.Save(stream);
            results.Add(new{page=test.Item2,width=ActualWidth,height=ActualHeight,scroll=PageScroller.ScrollableHeight,compact=NavColumn.ActualWidth<100,engine_ready=ready});
        }
        File.WriteAllText(Path.Combine(folder,"ui-checks.json"),JsonSerializer.Serialize(results,new JsonSerializerOptions{WriteIndented=true}));
        Close();
    }
}
