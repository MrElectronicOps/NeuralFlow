using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Nodes;
using Vortice.Direct3D;
using Vortice.Direct3D11;
using Vortice.DXGI;
using Vortice.D3DCompiler;
using Vortice.Mathematics;
using Windows.Graphics.Capture;
using Windows.Graphics.DirectX;
using Windows.Graphics.DirectX.Direct3D11;
using WinRT;

namespace NeuralFlow.Capture;

internal static class Native
{
    [DllImport("user32.dll")] internal static extern bool SetWindowDisplayAffinity(nint hwnd, uint affinity);
    [DllImport("user32.dll")] internal static extern bool SetLayeredWindowAttributes(nint hwnd, uint color, byte alpha, uint flags);
    [DllImport("user32.dll")] internal static extern bool SetWindowPos(nint hwnd, nint after, int x, int y, int width, int height, uint flags);
    [DllImport("user32.dll")] internal static extern bool ShowWindow(nint hwnd, int command);
    [DllImport("user32.dll")] internal static extern bool IsWindow(nint hwnd);
    [DllImport("user32.dll")] internal static extern bool IsIconic(nint hwnd);
    [DllImport("user32.dll")] internal static extern nint GetForegroundWindow();
    [DllImport("user32.dll")] internal static extern short GetAsyncKeyState(int key);
    [DllImport("user32.dll")] internal static extern bool GetWindowRect(nint hwnd, out Rect rect);
    [DllImport("user32.dll")] internal static extern bool GetMonitorInfo(nint monitor, ref MonitorInfo info);
    [DllImport("dwmapi.dll")] internal static extern int DwmGetWindowAttribute(nint hwnd, uint attribute, out Rect rect, uint length);
    [DllImport("d3d11.dll")] internal static extern int CreateDirect3D11DeviceFromDXGIDevice(nint dxgi, out nint inspectable);
    [DllImport("combase.dll")] internal static extern int WindowsCreateString([MarshalAs(UnmanagedType.LPWStr)] string text, int length, out nint result);
    [DllImport("combase.dll")] internal static extern int WindowsDeleteString(nint value);
    [DllImport("combase.dll")] internal static extern int RoGetActivationFactory(nint name, in Guid iid, out nint result);
    [StructLayout(LayoutKind.Sequential)] internal struct Rect { public int Left,Top,Right,Bottom; public int Width=>Right-Left; public int Height=>Bottom-Top; }
    [StructLayout(LayoutKind.Sequential)] internal struct MonitorInfo { public uint Size; public Rect Monitor,Work; public uint Flags; }
    [ComImport, Guid("3628E81B-3CAC-4C60-B7F4-23CE0E0C3356"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface ICaptureItemInterop
    {
        nint CreateForWindow(nint hwnd, in Guid iid);
        nint CreateForMonitor(nint monitor, in Guid iid);
    }
    [ComImport, Guid("A9B3D012-3DF2-4EE3-B8D1-8695F457D3C1"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IDirect3DDxgiInterfaceAccess { nint GetInterface(in Guid iid); }
    internal static GraphicsCaptureItem Item(nint target, bool monitor)
    {
        const string name="Windows.Graphics.Capture.GraphicsCaptureItem";
        Marshal.ThrowExceptionForHR(WindowsCreateString(name,name.Length,out nint str));
        nint ptr=0,item=0;
        try {
            Marshal.ThrowExceptionForHR(RoGetActivationFactory(str,typeof(ICaptureItemInterop).GUID,out ptr));
            var factory=(ICaptureItemInterop)Marshal.GetObjectForIUnknown(ptr);
            Guid iid=new("79C3F95B-31F7-4EC2-A464-632EF5D30760");
            item=monitor?factory.CreateForMonitor(target,iid):factory.CreateForWindow(target,iid);
            return MarshalInterface<GraphicsCaptureItem>.FromAbi(item);
        } finally { if(item!=0) Marshal.Release(item); if(ptr!=0) Marshal.Release(ptr); WindowsDeleteString(str); }
    }
}

internal sealed class Overlay : Form
{
    internal Overlay() { FormBorderStyle=FormBorderStyle.None; ShowInTaskbar=false; TopMost=true; Text="NeuralFlow overlay"; Bounds=new Rectangle(0,0,1,1); }
    protected override bool ShowWithoutActivation=>true;
    protected override CreateParams CreateParams { get { var p=base.CreateParams; p.ExStyle|=0x00080000|0x20|0x08000000|0x80; return p; } }
    protected override void WndProc(ref Message m) { if(m.Msg==0x84) {m.Result=(nint)(-1);return;} if(m.Msg==0x21) {m.Result=(nint)3;return;} base.WndProc(ref m); }
}

internal sealed class CaptureEngine : IDisposable
{
    readonly Overlay overlay;
    readonly HashSet<nint> controls=[];
    ID3D11Device? device;
    ID3D11DeviceContext? context;
    IDXGIFactory2? factory;
    IDirect3DDevice? winrtDevice;
    GraphicsCaptureItem? item;
    Direct3D11CaptureFramePool? pool;
    GraphicsCaptureSession? session;
    ID3D11Texture2D? source,residual,reference,small,staging;
    ID3D11ShaderResourceView? sourceView,residualView,referenceView;
    ID3D11RenderTargetView? backView,smallView;
    IDXGISwapChain1? swap;
    ID3D11VertexShader? vertex;
    ID3D11PixelShader? composite,resize;
    ID3D11SamplerState? sampler;
    ID3D11Buffer? constants;
    readonly Stopwatch clock=Stopwatch.StartNew();
    long serial,frames,shown;
    double lastFrame,lastResidual,started;
    bool active,visible,monitor,emergency,hasReference,dirty;
    nint target;
    int width,height,poolWidth,poolHeight,smallSize,residualSize;
    Native.Rect bounds;
    string error="",adapter="",pause="";
    float strength=.15f,clarity,saturation=1,contrast=1,brightness,warmth,tone;
    float[] parameters=new float[16];
    public CaptureEngine(Overlay window) { overlay=window; }
    public bool IsActive=>active;
    public void Start(nint handle,bool isMonitor)
    {
        Stop();
        if(!GraphicsCaptureSession.IsSupported()) throw new InvalidOperationException("Windows Graphics Capture is unavailable.");
        target=handle; monitor=isMonitor; emergency=false;
        try {
            factory=DXGI.CreateDXGIFactory1<IDXGIFactory2>();
            D3D11.D3D11CreateDevice(null,DriverType.Hardware,DeviceCreationFlags.BgraSupport,new[]{FeatureLevel.Level_11_1,FeatureLevel.Level_11_0},out device,out _,out context).CheckError();
            using var dxgi=device!.QueryInterface<IDXGIDevice>();
            using(var gpu=dxgi.GetAdapter()) adapter=gpu.Description.Description;
            Marshal.ThrowExceptionForHR(Native.CreateDirect3D11DeviceFromDXGIDevice(dxgi.NativePointer,out nint ptr));
            try {winrtDevice=MarshalInterface<IDirect3DDevice>.FromAbi(ptr);} finally {Marshal.Release(ptr);}
            item=Native.Item(handle,monitor);
            poolWidth=item.Size.Width;poolHeight=item.Size.Height;
            pool=Direct3D11CaptureFramePool.CreateFreeThreaded(winrtDevice,DirectXPixelFormat.B8G8R8A8UIntNormalized,2,item.Size);
            session=pool.CreateCaptureSession(item);
            session.IsCursorCaptureEnabled=false;
            try {session.IsBorderRequired=false;} catch { /* Windows may keep its capture indicator. */ }
            item.Closed+=ItemClosed;
            vertex=device.CreateVertexShader(Compiler.Compile(Shader,"VS","NeuralFlow.hlsl","vs_5_0").Span);
            composite=device.CreatePixelShader(Compiler.Compile(Shader,"Composite","NeuralFlow.hlsl","ps_5_0").Span);
            resize=device.CreatePixelShader(Compiler.Compile(Shader,"Resize","NeuralFlow.hlsl","ps_5_0").Span);
            sampler=device.CreateSamplerState(new SamplerDescription(Filter.MinMagMipLinear,TextureAddressMode.Clamp,TextureAddressMode.Clamp,TextureAddressMode.Clamp));
            constants=device.CreateBuffer(new BufferDescription(64,BindFlags.ConstantBuffer,ResourceUsage.Default));
            SetResidual(1,new float[3],null);
            if(!Native.SetWindowDisplayAffinity(overlay.Handle,0x11)) throw new InvalidOperationException("Cannot exclude the enhancement overlay from screen capture.");
            Native.SetLayeredWindowAttributes(overlay.Handle,0,255,2);
            session.StartCapture();
            active=true;error="";serial=frames=shown=0;started=clock.Elapsed.TotalSeconds;lastFrame=0;
        } catch {Stop();throw;}
    }
    void ItemClosed(GraphicsCaptureItem sender, object args) { active=false;error="The captured target was closed."; }
    public void Stop()
    {
        active=false;Hide();
        if(item!=null) item.Closed-=ItemClosed;
        session?.Dispose();session=null;pool?.Dispose();pool=null;item=null;
        context?.ClearState();
        backView?.Dispose();backView=null;swap?.Dispose();swap=null;
        // Flush deferred D3D destruction before creating another flip swapchain
        // for the same HWND on a later enable/target change.
        context?.Flush();
        sourceView?.Dispose();sourceView=null;source?.Dispose();source=null;
        residualView?.Dispose();residualView=null;residual?.Dispose();residual=null;
        referenceView?.Dispose();referenceView=null;reference?.Dispose();reference=null;
        smallView?.Dispose();smallView=null;small?.Dispose();small=null;staging?.Dispose();staging=null;
        vertex?.Dispose();vertex=null;composite?.Dispose();composite=null;resize?.Dispose();resize=null;sampler?.Dispose();sampler=null;constants?.Dispose();constants=null;
        (winrtDevice as IDisposable)?.Dispose();winrtDevice=null;context?.Dispose();context=null;device?.Dispose();device=null;factory?.Dispose();factory=null;
        width=height=smallSize=residualSize=0;hasReference=false;
    }
    public void Exclude(nint hwnd) { if(!Native.IsWindow(hwnd)) throw new ArgumentException("Control window is unavailable."); controls.Add(hwnd); }
    public void Parameters(JsonElement root)
    {
        static float Value(JsonElement r,string name,float current,float min,float max) => r.TryGetProperty(name,out var v) ? float.IsFinite(v.GetSingle())?Math.Clamp(v.GetSingle(),min,max):throw new ArgumentException("Nonfinite parameter.") : current;
        strength=Value(root,"strength",strength,0,1);clarity=Value(root,"clarity",clarity,0,1);saturation=Value(root,"saturation",saturation,0,2);contrast=Value(root,"contrast",contrast,.5f,1.5f);brightness=Value(root,"brightness",brightness,-.25f,.25f);warmth=Value(root,"warmth",warmth,-1,1);tone=Value(root,"tone",tone,0,1);
        dirty=true;
        if(IsNeutral()) Hide();
    }
    bool IsNeutral()=>strength==0&&clarity==0&&saturation==1&&contrast==1&&brightness==0&&warmth==0&&tone==0;
    public void Tick()
    {
        if((Native.GetAsyncKeyState(0x78)&0x8000)!=0) {emergency=true;Stop();return;}
        if(!active) {Hide();return;}
        try {
            if(!TargetBounds(out var next)) {pause="Target is minimized or unavailable";Hide();return;}
            bool moved=next.Left!=bounds.Left||next.Top!=bounds.Top||next.Width!=bounds.Width||next.Height!=bounds.Height;
            bounds=next;
            bool got=false;
            for(int i=0;i<3;i++) {
                using var frame=pool!.TryGetNextFrame();
                if(frame==null) break;
                if(frame.ContentSize.Width<1||frame.ContentSize.Height<1)continue;
                if(frame.ContentSize.Width!=poolWidth||frame.ContentSize.Height!=poolHeight) {
                    poolWidth=frame.ContentSize.Width;poolHeight=frame.ContentSize.Height;
                    pool.Recreate(winrtDevice!,DirectXPixelFormat.B8G8R8A8UIntNormalized,2,frame.ContentSize);
                    lastResidual=-100;continue;
                }
                var access=frame.Surface.As<Native.IDirect3DDxgiInterfaceAccess>();
                nint pointer=access.GetInterface(typeof(ID3D11Texture2D).GUID);
                using var texture=new ID3D11Texture2D(pointer);
                EnsureSource(frame.ContentSize.Width,frame.ContentSize.Height);
                context!.CopySubresourceRegion(source!,0,0,0,0,texture,0,new Box(0,0,0,width,height,1));
                got=true;serial++;frames++;lastFrame=clock.Elapsed.TotalSeconds;
            }
            bool foreground=monitor||Native.GetForegroundWindow()==target||controls.Contains(Native.GetForegroundWindow());
            if(!foreground) {pause="Paused while another application is in front";Hide();return;}
            // WGC intentionally emits no new frames for a static desktop. Retain
            // that valid texture and still update/fade the correction every tick.
            if(source==null) {pause="Waiting for a fresh frame";Hide();return;}
            pause="";
            if(IsNeutral()) {Hide();return;}
            if(got||moved||!visible||dirty||clock.Elapsed.TotalSeconds-lastResidual<1.1) {
                EnsureSwap();
                Render(backView!,width,height,false);
                swap!.Present(0,PresentFlags.DoNotWait);
                shown++;
                dirty=false;
                if(!visible||moved) {Native.SetWindowPos(overlay.Handle,(nint)(-1),bounds.Left,bounds.Top,width,height,0x10|0x40);visible=true;}
                // Cross-process controller positioning must not synchronously wait
                // for that UI thread while it is waiting for our protocol reply.
                foreach(var hwnd in controls) { if(Native.IsWindow(hwnd)&&hwnd!=target)Native.SetWindowPos(hwnd,(nint)(-1),0,0,0,0,0x4013); }
            }
        } catch(Exception e) {error=e.Message;Stop();}
    }
    bool TargetBounds(out Native.Rect rect)
    {
        if(monitor) {var info=new Native.MonitorInfo{Size=(uint)Marshal.SizeOf<Native.MonitorInfo>()};bool ok=Native.GetMonitorInfo(target,ref info);rect=info.Monitor;return ok&&rect.Width>0&&rect.Height>0;}
        if(!Native.IsWindow(target)||Native.IsIconic(target)) {rect=default;return false;}
        if(Native.DwmGetWindowAttribute(target,9,out rect,(uint)Marshal.SizeOf<Native.Rect>())!=0) Native.GetWindowRect(target,out rect);
        return rect.Width>0&&rect.Height>0;
    }
    void Hide() {if(visible)Native.ShowWindow(overlay.Handle,0);visible=false;}
    ID3D11Texture2D Texture(int w,int h,Format format,BindFlags bind,ResourceUsage usage=ResourceUsage.Default,CpuAccessFlags cpu=CpuAccessFlags.None)
        =>device!.CreateTexture2D(new Texture2DDescription(format,(uint)w,(uint)h,1,1,bind,usage,cpu));
    void EnsureSource(int w,int h)
    {
        if(source!=null&&w==width&&h==height)return;
        context!.PSSetShaderResource(0,null);sourceView?.Dispose();source?.Dispose();
        width=w;height=h;source=Texture(w,h,Format.B8G8R8A8_UNorm,BindFlags.ShaderResource);sourceView=device!.CreateShaderResourceView(source);lastResidual=-100;
    }
    void EnsureSwap()
    {
        if(swap!=null&&swap.Description1.Width==width&&swap.Description1.Height==height)return;
        context!.UnsetRenderTargets();backView?.Dispose();backView=null;
        if(swap!=null) swap.ResizeBuffers(2,(uint)width,(uint)height,Format.B8G8R8A8_UNorm,SwapChainFlags.None).CheckError();
        else swap=factory!.CreateSwapChainForHwnd(device!,overlay.Handle,new SwapChainDescription1{Width=(uint)width,Height=(uint)height,Format=Format.B8G8R8A8_UNorm,BufferCount=2,BufferUsage=Usage.RenderTargetOutput,SampleDescription=new SampleDescription(1,0),SwapEffect=SwapEffect.FlipSequential,Scaling=Scaling.Stretch,AlphaMode=AlphaMode.Ignore});
        using var back=swap.GetBuffer<ID3D11Texture2D>(0);backView=device!.CreateRenderTargetView(back);
    }
    unsafe void Render(ID3D11RenderTargetView view,int w,int h,bool isResize)
    {
        parameters[0]=strength;parameters[1]=clarity;parameters[2]=saturation;parameters[3]=contrast;
        parameters[4]=brightness;parameters[5]=warmth;parameters[6]=tone;parameters[7]=(float)Math.Clamp(1-(clock.Elapsed.TotalSeconds-lastResidual-.2)/.8,0,1);
        parameters[8]=width;parameters[9]=height;parameters[10]=hasReference?1:0;parameters[11]=0;
        fixed(float* p=parameters)context!.UpdateSubresource(constants!,0,null,(nint)p,0,0);
        context!.OMSetRenderTargets(view);context.RSSetViewport(0,0,w,h);
        context.IASetPrimitiveTopology(PrimitiveTopology.TriangleList);context.VSSetShader(vertex);context.PSSetShader(isResize?resize:composite);
        context.PSSetConstantBuffer(0,constants);context.PSSetSampler(0,sampler);context.PSSetShaderResource(0,sourceView);context.PSSetShaderResource(1,residualView);context.PSSetShaderResource(2,referenceView);
        context.Draw(3,0);context.UnsetRenderTargets();context.PSSetShaderResource(0,null);context.PSSetShaderResource(1,null);context.PSSetShaderResource(2,null);
    }
    public unsafe object Grab(int size)
    {
        if(!active||source==null)return new{ok=false,error=string.IsNullOrEmpty(error)?"No fresh captured frame":error};
        if(size<32||size>1024)throw new ArgumentOutOfRangeException(nameof(size));
        if(smallSize!=size) {smallView?.Dispose();small?.Dispose();staging?.Dispose();small=Texture(size,size,Format.B8G8R8A8_UNorm,BindFlags.RenderTarget);smallView=device!.CreateRenderTargetView(small);staging=Texture(size,size,Format.B8G8R8A8_UNorm,BindFlags.None,ResourceUsage.Staging,CpuAccessFlags.Read);smallSize=size;}
        Render(smallView!,size,size,true);context!.CopyResource(staging!,small!);context.Flush();
        var sw=Stopwatch.StartNew();MappedSubresource mapped;
        while(true) {var result=context.Map(staging!,0,MapMode.Read,Vortice.Direct3D11.MapFlags.DoNotWait,out mapped);if(result.Success)break;if(result.Code!=unchecked((int)0x887A000A)) result.CheckError();if(sw.ElapsedMilliseconds>30)return new{ok=false,error="GPU readback busy; try the newest frame"};Thread.Sleep(1);}
        byte[] rgb=new byte[size*size*3];
        try {for(int y=0;y<size;y++) {byte* row=(byte*)mapped.DataPointer+y*mapped.RowPitch;for(int x=0;x<size;x++){int off=(y*size+x)*3;rgb[off]=row[x*4+2];rgb[off+1]=row[x*4+1];rgb[off+2]=row[x*4];}}}finally{context.Unmap(staging!,0);}
        return new {ok=true,serial,size,width,height,rgb=Convert.ToBase64String(rgb),age_ms=(clock.Elapsed.TotalSeconds-lastFrame)*1000};
    }
    public unsafe void SetResidual(int size,float[] rgb,byte[]? referenceRgb)
    {
        if(device==null)throw new InvalidOperationException("Capture is not active.");
        if(size<1||size>1024||rgb.Length!=size*size*3||rgb.Any(v=>!float.IsFinite(v)))throw new ArgumentException("Invalid residual payload.");
        float[] rgba=new float[size*size*4];for(int p=0;p<size*size;p++){rgba[p*4]=Math.Clamp(rgb[p*3],-255,255)/255f;rgba[p*4+1]=Math.Clamp(rgb[p*3+1],-255,255)/255f;rgba[p*4+2]=Math.Clamp(rgb[p*3+2],-255,255)/255f;}
        if(residualSize!=size) {residualView?.Dispose();residual?.Dispose();referenceView?.Dispose();reference?.Dispose();residual=Texture(size,size,Format.R32G32B32A32_Float,BindFlags.ShaderResource);residualView=device.CreateShaderResourceView(residual);reference=Texture(size,size,Format.R8G8B8A8_UNorm,BindFlags.ShaderResource);referenceView=device.CreateShaderResourceView(reference);residualSize=size;}
        fixed(float* p=rgba)context!.UpdateSubresource(residual!,0,null,(nint)p,(uint)(size*16),0);
        hasReference=referenceRgb!=null&&referenceRgb.Length==size*size*3;
        byte[] refRgba=new byte[size*size*4];if(hasReference)for(int p=0;p<size*size;p++){refRgba[p*4]=referenceRgb![p*3];refRgba[p*4+1]=referenceRgb[p*3+1];refRgba[p*4+2]=referenceRgb[p*3+2];refRgba[p*4+3]=255;}
        fixed(byte* p=refRgba)context!.UpdateSubresource(reference!,0,null,(nint)p,(uint)(size*4),0);
        lastResidual=clock.Elapsed.TotalSeconds;
        dirty=true;
    }
    public object Status()=>new{ok=true,backend="Windows Graphics Capture / Direct3D 11",active,visible,emergency,adapter,width,height,frames,displayed_frames=shown,average_fps=frames/Math.Max(.001,clock.Elapsed.TotalSeconds-started),frame_age_ms=lastFrame==0?0:(clock.Elapsed.TotalSeconds-lastFrame)*1000,error,pause,target=(long)target,foreground=(long)Native.GetForegroundWindow(),overlay_hwnd=(long)overlay.Handle};
    public object ProbeVisiblePixel()
    {
        if(monitor||!visible)throw new InvalidOperationException("Visible-pixel diagnostics require an active window target.");
        try {
            Native.SetWindowDisplayAffinity(overlay.Handle,0);
            Thread.Sleep(70);
            using var bmp=new Bitmap(1,1);
            using(var g=Graphics.FromImage(bmp))g.CopyFromScreen(bounds.Left+width/2,bounds.Top+height*3/4,0,0,new System.Drawing.Size(1,1));
            var color=bmp.GetPixel(0,0);return new{ok=true,rgb=new int[]{color.R,color.G,color.B}};
        } finally {if(!Native.SetWindowDisplayAffinity(overlay.Handle,0x11))Stop();}
    }
    public void Dispose()=>Stop();
    const string Shader="""
        Texture2D Source:register(t0);Texture2D Residual:register(t1);Texture2D Reference:register(t2);SamplerState Samp:register(s0);
        cbuffer Params:register(b0){float strength;float clarity;float saturation;float contrast;float brightness;float warmth;float tone;float fade;float2 dimensions;float hasReference;float pad;float4 reserved;};
        struct V {float4 position:SV_POSITION;float2 uv:TEXCOORD0;};
        V VS(uint id:SV_VertexID){V v;v.uv=float2((id<<1)&2,id&2);v.position=float4(v.uv*float2(2,-2)+float2(-1,1),0,1);return v;}
        float2 Sq(float2 uv){float2 extent=dimensions/max(dimensions.x,dimensions.y);return uv*extent+(1-extent)*.5;}
        float4 Resize(V i):SV_TARGET {float2 extent=dimensions/max(dimensions.x,dimensions.y);float2 uv=(i.uv-(1-extent)*.5)/extent;if(any(uv<0)||any(uv>1))return float4(0,0,0,1);return float4(Source.Sample(Samp,uv).rgb,1);}
        float4 Composite(V i):SV_TARGET {
            float3 c=Source.Sample(Samp,i.uv).rgb;float2 square=Sq(i.uv);float3 ref=Reference.Sample(Samp,square).rgb;
            float confidence=hasReference>0?saturate(1-max(max(abs(c.r-ref.r),abs(c.g-ref.g)),abs(c.b-ref.b))/.14):1;
            c+=Residual.Sample(Samp,square).rgb*strength*fade*confidence*confidence;
            float2 px=1/dimensions;float3 blur=(Source.Sample(Samp,i.uv+float2(px.x,0)).rgb+Source.Sample(Samp,i.uv-float2(px.x,0)).rgb+Source.Sample(Samp,i.uv+float2(0,px.y)).rgb+Source.Sample(Samp,i.uv-float2(0,px.y)).rgb)*.25;
            c+=clamp(c-blur,-.08,.08)*clarity*.8;
            float lum=dot(c,float3(.2126,.7152,.0722));c=lerp(lum.xxx,c,saturation);c=(c-.5)*contrast+.5+brightness;c+=warmth*float3(.05,.006,-.05);c=lerp(c,c*c*(3-2*c),tone*.25);return float4(saturate(c),1);
        }
        """;
}

internal static class Program
{
    [STAThread] static void Main(string[] args)
    {
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
        using var overlay=new Overlay();var handle=overlay.Handle;
        using var engine=new CaptureEngine(overlay);
        using var timer=new System.Windows.Forms.Timer{Interval=8};timer.Tick+=(_,_)=>engine.Tick();timer.Start();
        // The emergency key is independent of both the Python inference process
        // and the UI/render thread. Exiting this isolated host makes Windows
        // remove its overlay even if a graphics driver call is stalled.
        var emergencyWatcher=new Thread(()=>{while(true){if(engine.IsActive&&(Native.GetAsyncKeyState(0x78)&0x8000)!=0){Console.Error.WriteLine("F9 emergency restoration");Environment.Exit(9);}Thread.Sleep(16);}}){IsBackground=true,Name="NeuralFlow emergency restoration"};emergencyWatcher.Start();
        Console.OutputEncoding=new System.Text.UTF8Encoding(false);
        Console.WriteLine(JsonSerializer.Serialize(new{ready=true,protocol=1,backend="wgc-d3d11"}));
        var reader=new Thread(()=>{
            try {string? line;while((line=Console.ReadLine())!=null){if(line.Length>20_000_000)break;using var parsed=JsonDocument.Parse(line);var command=parsed.RootElement.Clone();using var done=new ManualResetEventSlim();Exception? failure=null;object? response=null;
                overlay.BeginInvoke(()=>{try{var name=command.GetProperty("command").GetString();switch(name){
                    case "start":engine.Start((nint)command.GetProperty("target").GetInt64(),command.GetProperty("kind").GetString()=="monitor");response=engine.Status();break;
                    case "stop":engine.Stop();response=engine.Status();break;
                    case "status":response=engine.Status();break;
                    case "probe" when args.Contains("--diagnostics"):response=engine.ProbeVisiblePixel();break;
                    case "exclude":engine.Exclude((nint)command.GetProperty("hwnd").GetInt64());response=new{ok=true};break;
                    case "parameters":engine.Parameters(command);response=new{ok=true};break;
                    case "grab":response=engine.Grab(command.GetProperty("size").GetInt32());break;
                    case "residual":var bytes=Convert.FromBase64String(command.GetProperty("rgb").GetString()!);if(bytes.Length%4!=0)throw new ArgumentException("Float32 residual length is invalid");float[] f=new float[bytes.Length/4];Buffer.BlockCopy(bytes,0,f,0,bytes.Length);byte[]? reference=command.TryGetProperty("reference",out var r)?Convert.FromBase64String(r.GetString()!):null;engine.SetResidual(command.GetProperty("size").GetInt32(),f,reference);response=new{ok=true};break;
                    case "close":engine.Stop();response=new{ok=true};Application.ExitThread();break;
                    default:throw new ArgumentException("Unknown command");
                }}catch(Exception e){failure=e;}finally{done.Set();}});
                if(!done.Wait(15000)) {Console.WriteLine(JsonSerializer.Serialize(new{ok=false,error="Capture command timed out"}));Environment.Exit(10);}
                var result=JsonSerializer.SerializeToNode(failure==null?response:new{ok=false,error=failure.ToString()})!.AsObject();if(command.TryGetProperty("id",out var id))result["id"]=JsonNode.Parse(id.GetRawText());Console.WriteLine(result.ToJsonString());
            }}catch(Exception e){Console.Error.WriteLine(e.Message);}finally{try{overlay.BeginInvoke(()=>Application.ExitThread());}catch{}}
        }){IsBackground=true,Name="NeuralFlow capture protocol"};reader.Start();
        Application.Run();
    }
}
