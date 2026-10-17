using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Threading;

// Isolated launcher protocol fixture. It never loads UE or changes project files.
internal static class FakeRenderer
{
    private static readonly Dictionary<string, string> Options = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    private static string Session, StatusPath, LogPath;
    private static int Pid;

    private static int Main(string[] args)
    {
        Parse(args);
        Session = Get("OOWLaunchId", Get("OOWLaunchSession", Get("session", "missing-session")));
        StatusPath = Get("OOWLaunchStatus", Get("status", ""));
        LogPath = Get("abslog", Get("log", ""));
        Pid = Process.GetCurrentProcess().Id;
        string scenario = Get("scenario", "normal");
        int step = Number("step-ms", scenario == "slow" ? 2000 : 120);
        int hold = Number("hold-ms", 30000);
        string pidFile = Get("pid-file", "");
        if (pidFile.Length > 0) Append(pidFile, Pid.ToString(CultureInfo.InvariantCulture) + Environment.NewLine);
        Log("fixture started scenario=" + scenario + " pid=" + Pid + " session=" + Session);
        Thread.Sleep(Number("initial-delay-ms", 0));

        if (scenario == "wrapper-spawn-child")
        {
            SpawnChild("normal", 250);
            return Number("wrapper-exit-code", 0);
        }
        if (scenario == "actual-exit-with-helper")
        {
            Publish("renderer", "Fixture actual renderer started.", Session, Pid);
            SpawnChild("no-status", 0);
            Thread.Sleep(100);
            return 42;
        }
        if (scenario == "early-exit")
        {
            Publish("renderer", "Fixture renderer started.", Session, Pid);
            Log("Simulated early renderer exit; code 42.");
            return 42;
        }
        if (scenario == "no-status")
        {
            Log("OOW_DESKTOP_ATTACHED from unstructured log must not mean ready.");
            Thread.Sleep(hold);
            return 0;
        }
        if (scenario == "status-publication-error" || scenario == "foreign-log")
        {
            if (scenario == "status-publication-error")
                Log("OOW_STARTUP_ERROR session=" + Session + " pid=" + Pid + " detail=Status publication failed (fixture access denied). Renderer remains available.");
            else
            {
                Log("OOW_STARTUP_ERROR session=" + Session + " pid=" + Number("foreign-pid", 4) + " detail=Wrong process must be ignored.");
                Log("OOW_STARTUP_ERROR session=00000000000000000000000000000001 pid=" + Pid + " detail=Wrong session must be ignored.");
                Log("OOW_DESKTOP_ATTACHED and ready strings must never establish readiness.");
            }
            Thread.Sleep(hold);
            return 0;
        }
        if (scenario == "stale-session" || scenario == "foreign-pid")
        {
            Publish("ready", "Invalid evidence must not be accepted.",
                scenario == "stale-session" ? "00000000-0000-0000-0000-000000000001" : Session,
                scenario == "foreign-pid" ? Number("foreign-pid", 4) : Pid);
            Thread.Sleep(hold);
            return 0;
        }
        Publish("renderer", "Fixture renderer started.", Session, Pid);
        Thread.Sleep(step);
        Publish("scene", "Loading fixture scene.", Session, Pid);
        if (scenario == "wait-to-cancel")
        {
            Thread.Sleep(hold);
            return 0;
        }
        Thread.Sleep(step);
        Publish("desktop", "Connecting fixture desktop.", Session, Pid);
        Thread.Sleep(step);
        if (scenario == "attach-error")
        {
            Publish("error", "Desktop attachment failed (fixture error 1400); renderer remains available.", Session, Pid);
            Thread.Sleep(hold);
            return 7;
        }
        if (scenario == "duplicate")
        {
            Publish("duplicate", "An existing instance is already running; it was not closed.", Session, Pid);
            Thread.Sleep(200);
            return 0;
        }
        Publish("ready", "Fixture scene and desktop ready.", Session, Pid);
        Thread.Sleep(hold);
        return 0;
    }

    private static void Publish(string stage, string detail, string session, int pid)
    {
        string json = "{\"session\":" + Json(session) + ",\"pid\":" + pid + ",\"stage\":" + Json(stage) + ",\"detail\":" + Json(detail) + "}";
        if (StatusPath.Length > 0)
        {
            string directory = Path.GetDirectoryName(Path.GetFullPath(StatusPath));
            Directory.CreateDirectory(directory);
            string temporary = StatusPath + "." + Pid + ".tmp";
            File.WriteAllText(temporary, json, new UTF8Encoding(false));
            // Windows readers/antivirus can temporarily prevent replacement.
            for (int attempt = 0; ; attempt++)
            {
                try
                {
                    if (File.Exists(StatusPath)) File.Replace(temporary, StatusPath, null);
                    else File.Move(temporary, StatusPath);
                    break;
                }
                catch (IOException) { if (attempt == 20) throw; Thread.Sleep(10); }
            }
        }
        Log("stage=" + stage + " evidencePid=" + pid + " evidenceSession=" + session);
    }

    private static string Json(string value)
    {
        return "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "\\r").Replace("\n", "\\n") + "\"";
    }

    private static string Quote(string value)
    {
        // Fixture options contain no literal quotes; preserve whitespace and trailing backslashes.
        string trimmed = value.TrimEnd('\\');
        return "\"" + trimmed + new string('\\', 2 * (value.Length - trimmed.Length)) + "\"";
    }

    private static void SpawnChild(string scenario, int delay)
    {
        ProcessStartInfo info = new ProcessStartInfo(Process.GetCurrentProcess().MainModule.FileName);
        info.UseShellExecute = false;
        info.CreateNoWindow = true;
        StringBuilder childArgs = new StringBuilder();
        foreach (KeyValuePair<string, string> option in Options)
        {
            if (option.Key == "scenario" || option.Key == "initial-delay-ms") continue;
            childArgs.Append(" --").Append(option.Key).Append('=').Append(Quote(option.Value));
        }
        childArgs.Append(" --scenario=").Append(scenario).Append(" --initial-delay-ms=").Append(delay);
        info.Arguments = childArgs.ToString();
        using (Process child = Process.Start(info)) Log("spawned child pid=" + child.Id);
    }

    private static void Log(string message)
    {
        if (LogPath.Length > 0) Append(LogPath, DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture) + " " + message + Environment.NewLine);
    }

    private static void Append(string path, string content)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path)));
        using (FileStream stream = new FileStream(path, FileMode.Append, FileAccess.Write, FileShare.ReadWrite))
        using (StreamWriter writer = new StreamWriter(stream, new UTF8Encoding(false))) writer.Write(content);
    }

    private static void Parse(string[] args)
    {
        for (int index = 0; index < args.Length; index++)
        {
            string arg = args[index].TrimStart('-');
            int equals = arg.IndexOf('=');
            if (equals >= 0) Options[arg.Substring(0, equals)] = arg.Substring(equals + 1);
            else if (index + 1 < args.Length && !args[index + 1].StartsWith("-", StringComparison.Ordinal)) Options[arg] = args[++index];
            else Options[arg] = "true";
        }
    }

    private static string Get(string key, string fallback)
    {
        string value;
        return Options.TryGetValue(key, out value) ? value : fallback;
    }

    private static int Number(string key, int fallback)
    {
        int value;
        return int.TryParse(Get(key, ""), out value) ? Math.Max(0, value) : fallback;
    }
}
