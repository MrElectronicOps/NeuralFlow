using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Text.Json;

namespace NeuralFlow;
public sealed class EngineClient : IDisposable
{
    private Process? process;
    private readonly SemaphoreSlim writeLock = new(1,1);
    private readonly ConcurrentDictionary<long,TaskCompletionSource<JsonElement>> pending = new();
    private long nextId;
    public event Action<JsonElement>? Event;
    public event Action<string>? Failed;
    public async Task Start()
    {
        string python = Path.Combine(Paths.Root,"python","python.exe");
        string service = Path.Combine(Paths.Root,"engine","service.py");
        if (!File.Exists(python) || !File.Exists(service)) throw new FileNotFoundException("The app package is incomplete. Extract the entire NeuralFlow folder before opening it.");
        Directory.CreateDirectory(Paths.Data);
        var start = new ProcessStartInfo(python) { UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true,WorkingDirectory=Paths.Root };
        start.ArgumentList.Add(service);start.ArgumentList.Add("--data");start.ArgumentList.Add(Paths.Data);
        start.Environment["PYTHONUTF8"]="1";
        process = new Process{StartInfo=start,EnableRaisingEvents=true};process.Start();
        _ = Task.Run(async ()=>{
            try {
                while(await process.StandardOutput.ReadLineAsync() is string line){
                    try {
                        var root=JsonDocument.Parse(line).RootElement.Clone();
                        if(root.TryGetProperty("id",out var id)&&pending.TryRemove(id.GetInt64(),out var waiter)) {
                            if(root.TryGetProperty("ok",out var ok)&&!ok.GetBoolean()) waiter.TrySetException(new InvalidOperationException(root.GetProperty("error").GetString()));
                            else waiter.TrySetResult(root.TryGetProperty("data",out var data)?data.Clone():root);
                        } else Event?.Invoke(root);
                    }catch(JsonException){ File.AppendAllText(Path.Combine(Paths.Data,"engine-protocol.log"),line+Environment.NewLine); }
                }
                Failed?.Invoke("The local engine stopped. Effects have been restored. Reopen NeuralFlow to reconnect.");
            }catch(Exception e){Failed?.Invoke(e.Message);}
            finally {foreach(var waiter in pending.Values)waiter.TrySetException(new IOException("The engine disconnected."));pending.Clear();}
        });
        _ = Task.Run(async ()=>{try{while(await process.StandardError.ReadLineAsync() is string line)File.AppendAllText(Path.Combine(Paths.Data,"engine.log"),line+Environment.NewLine);}catch{};});
        await Send("status");
    }
    public async Task<JsonElement> Send(string op,object? payload=null,int timeout=120000)
    {
        if(process is null||process.HasExited)throw new IOException("Local engine is not running.");
        long id=Interlocked.Increment(ref nextId);var task=new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);pending[id]=task;
        var fields=payload is null?new Dictionary<string,object?>():JsonSerializer.Deserialize<Dictionary<string,object?>>(JsonSerializer.Serialize(payload))!;
        fields["id"]=id;fields["op"]=op;
        await writeLock.WaitAsync();try{await process.StandardInput.WriteLineAsync(JsonSerializer.Serialize(fields));await process.StandardInput.FlushAsync();}finally{writeLock.Release();}
        try{return await task.Task.WaitAsync(TimeSpan.FromMilliseconds(timeout));}finally{pending.TryRemove(id,out _);}
    }
    public void Dispose(){if(process is null)return;try{process.StandardInput.WriteLine("{\"op\":\"shutdown\",\"id\":-1}");if(!process.WaitForExit(2000))process.Kill(true);}catch{}process.Dispose();process=null;}
}
