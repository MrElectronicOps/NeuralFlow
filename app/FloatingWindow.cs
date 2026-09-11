using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

namespace NeuralFlow;
public sealed class FloatingWindow : Window
{
    public FloatingWindow(MainWindow owner)
    {
        Owner=owner;Title="NeuralFlow controls";Width=340;SizeToContent=SizeToContent.Height;ResizeMode=ResizeMode.NoResize;Topmost=true;ShowInTaskbar=false;
        WindowStyle=WindowStyle.ToolWindow;var panel=new StackPanel{Margin=new Thickness(18)};Content=panel;
        var title=new TextBlock{Text="NEURALFLOW / LIVE",FontSize=14,Foreground=Brushes.LightCyan,Margin=new Thickness(0,0,0,14)};title.MouseLeftButtonDown+=(_,e)=>{if(e.ButtonState==MouseButtonState.Pressed)DragMove();};panel.Children.Add(title);
        var row=new WrapPanel();panel.Children.Add(row);
        var power=new Button{Content="ON / OFF",Margin=new Thickness(0,0,8,8)};power.Click+=async(_,__)=>await owner.Toggle();row.Children.Add(power);
        var compare=new Button{Content="Hold original",Margin=new Thickness(0,0,0,8)};compare.PreviewMouseLeftButtonDown+=async(_,e)=>{compare.CaptureMouse();await owner.Compare(true);e.Handled=true;};compare.PreviewMouseLeftButtonUp+=async(_,e)=>{compare.ReleaseMouseCapture();await owner.Compare(false);e.Handled=true;};compare.LostMouseCapture+=async(_,__)=>await owner.Compare(false);compare.PreviewKeyDown+=async(_,e)=>{if(e.Key==Key.Space)await owner.Compare(true);};compare.PreviewKeyUp+=async(_,e)=>{if(e.Key==Key.Space)await owner.Compare(false);};row.Children.Add(compare);
        foreach(var pair in new[]{("Strength",owner.StrengthControl),("Stability",owner.StabilityControl)}){panel.Children.Add(new TextBlock{Text=pair.Item1,Margin=new Thickness(0,8,0,0)});var slider=new Slider{Minimum=0,Maximum=100};slider.SetBinding(Slider.ValueProperty,new System.Windows.Data.Binding("Value"){Source=pair.Item2,Mode=System.Windows.Data.BindingMode.TwoWay});System.Windows.Automation.AutomationProperties.SetName(slider,pair.Item1);panel.Children.Add(slider);}
        foreach(var slider in panel.Children.OfType<Slider>())slider.SetBinding(IsEnabledProperty,new System.Windows.Data.Binding("IsEnabled"){Source=slider==panel.Children.OfType<Slider>().First()?owner.StrengthControl:owner.StabilityControl});
        var status=new TextBlock{FontSize=13,TextWrapping=TextWrapping.Wrap,Foreground=Brushes.LightGray};status.SetBinding(TextBlock.TextProperty,new System.Windows.Data.Binding("Text"){Source=owner.StatusControl});panel.Children.Add(status);
        Closed+=async(_,__)=>await owner.Compare(false);
    }
}
