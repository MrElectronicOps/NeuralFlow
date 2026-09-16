using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Input;
using System.Windows.Media;
namespace NeuralFlow;
public sealed class FloatingWindow : Window
{
    public FloatingWindow(MainWindow main)
    {
        // Independent window: WPF owned windows minimize with their owner.
        Title="NeuralFlow controls";Width=370;Height=430;MinWidth=310;MinHeight=280;
        ResizeMode=ResizeMode.CanResizeWithGrip;Topmost=true;ShowInTaskbar=false;
        WindowStyle=WindowStyle.ToolWindow;Background=new SolidColorBrush(Color.FromRgb(15,23,34));
        Foreground=Brushes.White;FontFamily=new FontFamily("Segoe UI");FontSize=15;
        SourceInitialized+=(_,__)=>{
            var source=System.Windows.Interop.HwndSource.FromHwnd(new System.Windows.Interop.WindowInteropHelper(this).Handle);
            if(source?.CompositionTarget is not null)source.CompositionTarget.RenderMode=System.Windows.Interop.RenderMode.SoftwareOnly;
        };
        var panel=new StackPanel{Margin=new Thickness(20)};
        Content=new ScrollViewer{Content=panel,VerticalScrollBarVisibility=ScrollBarVisibility.Auto};
        var heading=new TextBlock{Text="NEURALFLOW",FontSize=20,FontWeight=FontWeights.SemiBold,Foreground=Brushes.LightCyan};
        heading.MouseLeftButtonDown+=(_,e)=>{if(e.ButtonState==MouseButtonState.Pressed)DragMove();};panel.Children.Add(heading);
        panel.Children.Add(new TextBlock{Text="LIVE CONTROLS",FontSize=11,Foreground=Brushes.LightGray,Margin=new Thickness(0,3,0,16)});
        var power=new Button{Margin=new Thickness(0,0,0,10)};power.SetBinding(ContentProperty,new Binding("Content"){Source=main.PowerControl});
        power.Click+=async(_,__)=>await main.Toggle();panel.Children.Add(power);
        var compare=new Button{Content="Hold to compare original",Margin=new Thickness(0,0,0,10)};
        compare.PreviewMouseLeftButtonDown+=async(_,e)=>{compare.CaptureMouse();await main.Compare(true);e.Handled=true;};
        compare.PreviewMouseLeftButtonUp+=async(_,e)=>{compare.ReleaseMouseCapture();await main.Compare(false);e.Handled=true;};
        compare.LostMouseCapture+=async(_,__)=>await main.Compare(false);
        compare.PreviewKeyDown+=async(_,e)=>{if(e.Key==Key.Space){await main.Compare(true);e.Handled=true;}};
        compare.PreviewKeyUp+=async(_,e)=>{if(e.Key==Key.Space){await main.Compare(false);e.Handled=true;}};panel.Children.Add(compare);
        void AddSlider(Panel parent,string label,Slider source)
        {
            var row=new DockPanel{Margin=new Thickness(0,7,0,0)};
            var value=new TextBlock{Foreground=Brushes.LightCyan};value.SetBinding(TextBlock.TextProperty,new Binding("Value"){Source=source,StringFormat="{0:0}%"});DockPanel.SetDock(value,Dock.Right);row.Children.Add(value);row.Children.Add(new TextBlock{Text=label});parent.Children.Add(row);
            var slider=new Slider{Minimum=source.Minimum,Maximum=source.Maximum};slider.SetBinding(Slider.ValueProperty,new Binding("Value"){Source=source,Mode=BindingMode.TwoWay});slider.SetBinding(IsEnabledProperty,new Binding("IsEnabled"){Source=source});slider.SetBinding(ToolTipProperty,new Binding("ToolTip"){Source=source});System.Windows.Automation.AutomationProperties.SetName(slider,label);parent.Children.Add(slider);
        }
        AddSlider(panel,"Neural strength",main.StrengthControl);
        var morePanel=new StackPanel();AddSlider(morePanel,"Stability",main.StabilityControl);
        foreach(var (label,control) in main.MoreControls)AddSlider(morePanel,label,control);
        var open=new Button{Content="Open full settings",Margin=new Thickness(0,10,0,8)};open.Click+=(_,__)=>main.RestoreMainWindow();morePanel.Children.Add(open);
        panel.Children.Add(new Expander{Header="More · stability & picture",Content=morePanel});
        var status=new TextBlock{FontSize=12,TextWrapping=TextWrapping.Wrap,Foreground=Brushes.LightGray,Margin=new Thickness(0,14,0,0)};status.SetBinding(TextBlock.TextProperty,new Binding("Text"){Source=main.StatusControl});panel.Children.Add(status);
        Deactivated+=async(_,__)=>await main.Compare(false);Closed+=async(_,__)=>await main.Compare(false);
    }
}
