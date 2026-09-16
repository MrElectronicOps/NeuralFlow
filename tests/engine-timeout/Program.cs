using System.Diagnostics;
using System.Reflection;
using NeuralFlow;
var start=new ProcessStartInfo(args[0]){UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true};
start.ArgumentList.Add("-c");start.ArgumentList.Add("import time; time.sleep(30)");
using var process=Process.Start(start)!;
using var client=new EngineClient();
typeof(EngineClient).GetField("process",BindingFlags.NonPublic|BindingFlags.Instance)!.SetValue(client,process);
var timer=Stopwatch.StartNew();
try{await client.Send("settings",new{value=1},250);throw new Exception("Unresponsive engine did not time out");}
catch(TimeoutException){if(!process.WaitForExit(3000))throw new Exception("Unresponsive engine survived");if(timer.ElapsedMilliseconds>4000)throw new Exception("Deadline was not bounded");Console.WriteLine("PASS: unresponsive engine timed out and exited; UI caller received a recoverable exception");}
namespace NeuralFlow { public static class Paths { public static string Root=>AppContext.BaseDirectory;public static string Data=>Path.GetTempPath(); } }
