using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using OutOfWindow.Launcher;

internal static class LaunchSessionTests
{
    static string Fixture, RunDirectory;
    static List<object> Results = new List<object>();
    static int Failures;

    static int Main(string[] args)
    {
        Fixture = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "FakeRenderer.exe");
        RunDirectory = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "results", DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        Directory.CreateDirectory(RunDirectory);
        Run("normal-stage-order", Normal);
        Run("slow-load-stays-loading", Slow);
        Run("early-exit-retains-42", EarlyExit);
        Run("unbound-exit-labelled-launch-entry", UnboundExit);
        Run("missing-executable-retains-error", MissingExecutable);
        Run("attachment-failure-explicit", AttachmentFailure);
        Run("status-publication-error-log-fallback", PublicationError);
        Run("foreign-error-log-ignored", ForeignErrorLog);
        Run("old-log-marker-not-ready", NoStatus);
        Run("wrong-session-not-ready", WrongSession);
        Run("foreign-pid-not-ready", ForeignPid);
        Run("wrapper-exits-child-reaches-ready", Wrapper);
        Run("cancel-only-owned-processes", CancelOnlyOwned);
        Run("retry-new-session-recovers", Retry);
        Run("repeat-start-replaces-only-owned", RepeatStart);
        Run("retry-waits-for-retained-process-exit", RetryWaitsForExit);
        Run("retry-timeout-preserves-owned-session", RetryTimeout);
        Run("duplicate-preserves-existing-process", Duplicate);
        Run("actual-exit-not-blocked-by-helper", ActualExitWithHelper);
        Run("ready-then-exited-is-observed", ExitedAfterReady);
        Run("dispose-does-not-kill-renderer", DisposeKeepsRenderer);
        string report = Path.Combine(RunDirectory, "results.json");
        File.WriteAllText(report, new JavaScriptSerializer().Serialize(new { fixture = Fixture, tests = Results, failures = Failures, note = "Isolated Windows process tests; no UE scene, WorkerW, or GUI rendering validation." }), new UTF8Encoding(false));
        Console.WriteLine("RESULTS=" + report);
        Console.WriteLine("TESTS=" + Results.Count + " FAILURES=" + Failures);
        return Failures == 0 ? 0 : 1;
    }

    static LaunchSession Session() { return new LaunchSession(Path.Combine(RunDirectory, "sessions")); }
    static void Start(LaunchSession session, string scenario, string extra)
    {
        session.Start(Fixture, "--scenario=" + scenario + " -OOWLaunchId={session} -OOWLaunchStatus=\"{status}\" -abslog=\"{log}\" --hold-ms=10000 " + extra, Path.GetDirectoryName(Fixture));
    }
    static void Run(string name, Func<string> test)
    {
        Stopwatch timer = Stopwatch.StartNew();
        try
        {
            string evidence = test();
            Results.Add(new { name = name, passed = true, milliseconds = timer.ElapsedMilliseconds, evidence = evidence });
            Console.WriteLine("PASS " + name + " " + evidence);
        }
        catch (Exception error)
        {
            Failures++;
            Results.Add(new { name = name, passed = false, milliseconds = timer.ElapsedMilliseconds, evidence = error.ToString() });
            Console.WriteLine("FAIL " + name + " " + error.Message);
        }
    }
    static void Assert(bool condition, string message) { if (!condition) throw new Exception(message); }
    static bool Wait(LaunchSession session, Func<bool> predicate, int limit)
    {
        Stopwatch timer = Stopwatch.StartNew();
        do { session.Poll(); if (predicate()) return true; Thread.Sleep(20); } while (timer.ElapsedMilliseconds < limit);
        session.Poll();
        return predicate();
    }
    static void ObserveLoading(LaunchSession session, int milliseconds)
    {
        Stopwatch timer = Stopwatch.StartNew();
        do { session.Poll(); Assert(session.IsLoading, "Expected Loading, got " + session.State + ": " + session.Detail); Thread.Sleep(20); } while (timer.ElapsedMilliseconds < milliseconds);
    }
    static bool Alive(int pid)
    {
        try { using (Process process = Process.GetProcessById(pid)) return !process.HasExited; }
        catch (ArgumentException) { return false; }
    }
    static void AssertStopped(int pid)
    {
        Stopwatch timer = Stopwatch.StartNew();
        while (Alive(pid) && timer.ElapsedMilliseconds < 2000) Thread.Sleep(20);
        Assert(!Alive(pid), "Owned PID " + pid + " survived cancellation.");
    }
    static void Finish(LaunchSession session) { if (session.HasProcesses) session.Cancel(); session.Dispose(); }
    static string Normal()
    {
        LaunchSession session = Session();
        try
        {
            Start(session, "normal", "--step-ms=160");
            List<string> stages = new List<string>();
            Assert(Wait(session, delegate { if (!stages.Contains(session.Stage)) stages.Add(session.Stage); return session.State == LaunchState.Ready; }, 4000), session.Detail);
            Assert(String.Join(",", stages.ToArray()) == "renderer,scene,desktop,ready", "Observed " + String.Join(",", stages.ToArray()));
            Assert(session.ActualPid.HasValue && Alive(session.ActualPid.Value), "Ready needs a live actual process.");
            return "stages=" + String.Join(",", stages.ToArray()) + "; actualPid=" + session.ActualPid + "; " + session.DirectoryPath;
        }
        finally { Finish(session); }
    }
    static string Slow()
    {
        LaunchSession session = Session();
        try { Start(session, "slow", "--step-ms=1000"); ObserveLoading(session, 1400); Assert(session.ElapsedSeconds >= 1, "Elapsed timer did not advance."); return "still " + session.Stage + " after " + session.ElapsedSeconds.ToString("F2") + "s; no false failure"; }
        finally { Finish(session); }
    }
    static string EarlyExit()
    {
        LaunchSession session = Session();
        try { Start(session, "early-exit", ""); Assert(Wait(session, delegate { return session.State == LaunchState.Failed && session.ExitCode.HasValue; }, 3000), session.State + ": " + session.Detail); Assert(session.ExitCode == 42, "Wrong exit code " + session.ExitCode); Assert(session.ExitCodeLabel.Contains("UE"), "Bound renderer exit label lost."); Assert(File.Exists(session.LogPath), "Error log missing."); return "UE exit=42; " + session.DirectoryPath; }
        finally { Finish(session); }
    }
    static string UnboundExit()
    {
        LaunchSession session = Session();
        try { Start(session, "no-status", "--hold-ms=20"); Assert(Wait(session, delegate { return session.State == LaunchState.Failed && session.ExitCode.HasValue; }, 3000), "Unbound exit not observed."); Assert(!session.ActualPid.HasValue && session.ExitCodeLabel.Contains("启动入口"), "Unbound wrapper code mislabelled as UE."); return "exit without owned protocol PID correctly labelled launch entry, not UE"; }
        finally { Finish(session); }
    }
    static string MissingExecutable()
    {
        LaunchSession session = Session();
        try { session.Start(Path.Combine(RunDirectory, "missing.exe"), "", RunDirectory); session.Poll(); Assert(session.State == LaunchState.Failed && !String.IsNullOrWhiteSpace(session.Detail), "Missing executable did not retain clear failure."); Assert(File.Exists(Path.Combine(session.DirectoryPath, "launcher.log")), "Launcher error log missing."); return session.Detail + "; " + session.DirectoryPath; }
        finally { Finish(session); }
    }
    static string AttachmentFailure()
    {
        LaunchSession session = Session();
        try { Start(session, "attach-error", ""); Assert(Wait(session, delegate { return session.State == LaunchState.Failed; }, 3000), "Attachment error not observed."); Assert(session.Detail.Contains("1400"), "Attachment error detail lost."); Assert(session.CanCancel, "Failed owned renderer cannot be cancelled."); return session.Detail + "; error state cancellation enabled"; }
        finally { Finish(session); }
    }
    static string PublicationError()
    {
        LaunchSession session = Session();
        try
        {
            Start(session, "status-publication-error", "");
            Assert(Wait(session, delegate { return session.State == LaunchState.Failed; }, 3000), "Explicit owned log failure not recognized.");
            Assert(!File.Exists(session.StatusPath), "Fixture unexpectedly published status.");
            Assert(session.Detail.Contains("Status publication failed") && session.ActualPid.HasValue, "Failure detail or owned PID lost.");
            Assert(session.CanCancel, "Error state does not allow cancelling live owned renderer.");
            int pid = session.ActualPid.Value; session.Cancel(); AssertStopped(pid);
            return "explicit same-session owned-PID log failure recognized without status.json; owned process cancelled";
        }
        finally { Finish(session); }
    }
    static string ForeignErrorLog()
    {
        LaunchSession session = Session();
        try { Start(session, "foreign-log", "--foreign-pid=" + Process.GetCurrentProcess().Id); ObserveLoading(session, 1400); Assert(!session.ActualPid.HasValue, "Foreign log bound actual renderer."); return "matching-session foreign PID and mismatched-session owned PID errors ignored; logs did not establish Ready"; }
        finally { Finish(session); }
    }
    static string NoStatus()
    {
        LaunchSession session = Session();
        try { Start(session, "no-status", ""); ObserveLoading(session, 400); Assert(File.ReadAllText(session.LogPath).Contains("OOW_DESKTOP_ATTACHED"), "Fixture marker missing."); return "unstructured OOW_DESKTOP_ATTACHED ignored; actualPid=" + session.ActualPid; }
        finally { Finish(session); }
    }
    static string WrongSession()
    {
        LaunchSession session = Session();
        try { Start(session, "stale-session", ""); ObserveLoading(session, 400); Assert(!session.ActualPid.HasValue, "Wrong-session PID trusted."); return "foreign session ready ignored"; }
        finally { Finish(session); }
    }
    static string ForeignPid()
    {
        LaunchSession session = Session();
        try { Start(session, "foreign-pid", "--foreign-pid=" + Process.GetCurrentProcess().Id); ObserveLoading(session, 400); Assert(!session.ActualPid.HasValue, "Foreign process trusted."); return "matching session but external live PID ignored"; }
        finally { Finish(session); }
    }
    static string Wrapper()
    {
        LaunchSession session = Session();
        try
        {
            string pidsFile = Path.Combine(RunDirectory, "wrapper-pids.txt");
            Start(session, "wrapper-spawn-child", "--wrapper-exit-code=17 --pid-file=" + LaunchSession.Quote(pidsFile));
            Assert(Wait(session, delegate { return session.State == LaunchState.Ready; }, 4000), session.State + ": " + session.Detail);
            int[] pids = File.ReadAllLines(pidsFile).Select(Int32.Parse).ToArray();
            Assert(pids.Length == 2 && session.ActualPid == pids[1] && pids[0] != pids[1], "Did not track actual child.");
            Assert(!Alive(pids[0]) && Alive(pids[1]), "Wrapper/child lifetimes incorrect.");
            session.Cancel(); AssertStopped(pids[1]);
            return "wrapper=" + pids[0] + " exited 17; actual=" + pids[1] + " reached ready then owned cancel";
        }
        finally { Finish(session); }
    }
    static Process External()
    {
        ProcessStartInfo info = new ProcessStartInfo(Fixture, "--scenario=no-status --hold-ms=15000");
        info.UseShellExecute = false; info.CreateNoWindow = true;
        return Process.Start(info);
    }
    static void StopExternal(Process process) { if (!process.HasExited) process.Kill(); process.WaitForExit(); process.Dispose(); }
    static string CancelOnlyOwned()
    {
        LaunchSession session = Session(); Process external = External();
        try
        {
            Start(session, "wait-to-cancel", ""); Assert(Wait(session, delegate { return session.ActualPid.HasValue; }, 3000), "No actual PID.");
            int owned = session.ActualPid.Value; session.Cancel(); AssertStopped(owned); Assert(session.State == LaunchState.Cancelled, "Not cancelled."); Assert(!external.HasExited, "External process was terminated.");
            return "owned=" + owned + " stopped; external=" + external.Id + " preserved";
        }
        finally { Finish(session); StopExternal(external); }
    }
    static string Retry()
    {
        LaunchSession session = Session();
        try
        {
            Start(session, "early-exit", ""); Assert(Wait(session, delegate { return session.State == LaunchState.Failed; }, 3000), "Initial failure missing.");
            string oldId = session.Id, oldStatus = session.StatusPath, oldLog = session.LogPath;
            File.WriteAllText(oldStatus, "{\"session\":\"" + oldId + "\",\"pid\":4,\"stage\":\"ready\",\"detail\":\"historical\"}");
            Start(session, "normal", "--step-ms=80"); Assert(session.Id != oldId && session.StatusPath != oldStatus && session.LogPath != oldLog, "Retry reused evidence paths.");
            Assert(Wait(session, delegate { return session.State == LaunchState.Ready; }, 3000), "Retry did not recover: " + session.Detail);
            return "new GUID/status/log; previous failure evidence retained; retry Ready";
        }
        finally { Finish(session); }
    }
    static string RepeatStart()
    {
        LaunchSession session = Session(); Process external = External();
        try
        {
            Start(session, "wait-to-cancel", ""); Assert(Wait(session, delegate { return session.ActualPid.HasValue; }, 3000), "No initial actual PID.");
            int first = session.ActualPid.Value; string firstId = session.Id;
            Start(session, "normal", "--step-ms=80"); AssertStopped(first); Assert(session.Id != firstId, "Repeated start reused session.");
            Assert(Wait(session, delegate { return session.State == LaunchState.Ready; }, 3000), "Repeated launch failed."); Assert(!external.HasExited, "External process terminated.");
            return "replaced owned=" + first + "; new=" + session.ActualPid + "; external=" + external.Id + " preserved";
        }
        finally { Finish(session); StopExternal(external); }
    }
    static string Duplicate()
    {
        LaunchSession session = Session(); Process external = External();
        try { Start(session, "duplicate", "--step-ms=10"); Assert(Wait(session, delegate { return session.State == LaunchState.Duplicate; }, 3000), "Duplicate not recognized."); Thread.Sleep(300); session.Poll(); Assert(session.State == LaunchState.Duplicate, "Duplicate overwritten after exit."); Assert(!external.HasExited, "Existing process killed."); return "Duplicate retained after fixture exit; existing=" + external.Id + " preserved"; }
        finally { Finish(session); StopExternal(external); }
    }
    static string RetryWaitsForExit() { return RetryWithEmptyJob(false); }
    static string RetryTimeout() { return RetryWithEmptyJob(true); }
    static string RetryWithEmptyJob(bool timeout)
    {
        LaunchSession session = Session();
        IntPtr originalJob = IntPtr.Zero, emptyJob = IntPtr.Zero;
        string previousId = null;
        FieldInfo jobField = typeof(LaunchSession).GetField("job", BindingFlags.Instance | BindingFlags.NonPublic);
        try
        {
            Start(session, "normal", "--step-ms=10 --hold-ms=" + (timeout ? "6000" : "900"));
            Assert(Wait(session, delegate { return session.State == LaunchState.Ready; }, 3000), "Initial fixture did not reach ready.");
            previousId = session.Id;
            int previousPid = session.ActualPid.Value;
            originalJob = (IntPtr)jobField.GetValue(session);
            emptyJob = Native.CreateJobObject(IntPtr.Zero, null);
            Assert(emptyJob != IntPtr.Zero, "Could not create isolated empty-job fixture.");
            // Model the brief native observation: the job is empty while retained process handles remain live.
            // The real fixture job is retained here and restored for cleanup on the timeout path.
            jobField.SetValue(session, emptyJob);
            Stopwatch elapsed = Stopwatch.StartNew();
            Start(session, "normal", "--step-ms=10");
            long milliseconds = elapsed.ElapsedMilliseconds;
            if (timeout)
            {
                Assert(milliseconds >= 1900 && milliseconds < 3500, "Retry timeout was not bounded near 2 seconds: " + milliseconds);
                Assert(session.State == LaunchState.Failed && session.Id == previousId && session.ActualPid == previousPid, "Timeout replaced/disposed the prior session.");
                Assert((IntPtr)jobField.GetValue(session) == emptyJob && session.CanCancel, "Timeout lost its job or cancellation capability.");
                Assert(session.Detail.Contains("仍在退出") && Alive(previousPid), "Timeout did not clearly preserve a live prior process.");
                return "2-second timeout retained session/PID/job and CanCancel; no new process launched (isolated empty-job state injection)";
            }
            Assert(milliseconds >= 500 && milliseconds < 2500, "Retry did not wait for retained prior process: " + milliseconds);
            Assert(session.Id != previousId && !Alive(previousPid), "New launch started before prior retained process exited.");
            Assert(Wait(session, delegate { return session.State == LaunchState.Ready; }, 3000), "Retry did not recover after prior exit.");
            return "waited " + milliseconds + "ms for retained prior process, then new session Ready (isolated empty-job state injection)";
        }
        finally
        {
            if (originalJob != IntPtr.Zero)
            {
                if (session.Id == previousId)
                {
                    jobField.SetValue(session, originalJob);
                    if (emptyJob != IntPtr.Zero) Native.CloseHandle(emptyJob);
                }
                else Native.CloseHandle(originalJob);
            }
            Finish(session);
        }
    }
    static string ActualExitWithHelper()
    {
        LaunchSession session = Session();
        try { Start(session, "actual-exit-with-helper", "--hold-ms=4000"); Assert(Wait(session, delegate { return session.State == LaunchState.Failed && session.ExitCode == 42; }, 1000), "Actual renderer exited 42 but state=" + session.State + ", code=" + session.ExitCode + ", helperAlive=" + session.HasProcesses); return "renderer exit 42 reported while owned helper remains alive=" + session.HasProcesses; }
        finally { Finish(session); }
    }
    static string ExitedAfterReady()
    {
        LaunchSession session = Session();
        try { Start(session, "normal", "--step-ms=30 --hold-ms=250"); Assert(Wait(session, delegate { return session.State == LaunchState.Ready; }, 3000), "Never ready."); Assert(Wait(session, delegate { return session.State == LaunchState.Exited; }, 3000), "Renderer exit not observed."); Assert(session.ExitCode == 0, "Successful exit code lost."); return "Ready -> Exited, exit=0; observer remains running"; }
        finally { Finish(session); }
    }
    static string DisposeKeepsRenderer()
    {
        LaunchSession session = Session(); Process actual = null;
        try
        {
            Start(session, "normal", "--step-ms=20 --hold-ms=800"); Assert(Wait(session, delegate { return session.State == LaunchState.Ready; }, 3000), "Never ready.");
            actual = Process.GetProcessById(session.ActualPid.Value); int pid = actual.Id; session.Dispose(); Thread.Sleep(100); Assert(!actual.HasExited, "Dispose killed owned renderer."); Assert(actual.WaitForExit(3000), "Fixture did not naturally exit.");
            return "Dispose preserved PID " + pid + "; fixture exited naturally";
        }
        finally { if (actual != null) { if (!actual.HasExited) actual.Kill(); actual.Dispose(); } session.Dispose(); }
    }
}
