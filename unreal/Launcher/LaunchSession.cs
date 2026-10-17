using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

namespace OutOfWindow.Launcher
{
    public enum LaunchState { Starting, Loading, Ready, Failed, Exited, Cancelled, Duplicate }

    // A job assigned before the first thread runs owns this launch, including bootstrap children.
    // No KILL_ON_JOB_CLOSE: closing the launcher after readiness leaves the scene running.
    public sealed class LaunchSession : IDisposable
    {
        readonly string sessionsRoot;
        readonly Stopwatch clock = new Stopwatch();
        IntPtr job;
        Process root, actual;
        string failure;
        double nextLogCheck;
        public string Id { get; private set; }
        public string DirectoryPath { get; private set; }
        public string StatusPath { get; private set; }
        public string LogPath { get; private set; }
        public string Stage { get; private set; }
        public string Detail { get; private set; }
        public int? ActualPid { get; private set; }
        public int? ExitCode { get; private set; }
        public string ExitCodeLabel { get { return ActualPid.HasValue ? "UE 退出码" : "启动入口退出码（尚未确认 UE 进程）"; } }
        public LaunchState State { get; private set; }
        public bool IsLoading { get { return State == LaunchState.Starting || State == LaunchState.Loading; } }
        public bool CanCancel { get { return job != IntPtr.Zero && (IsLoading || State == LaunchState.Failed); } }
        public double ElapsedSeconds { get { return clock.Elapsed.TotalSeconds; } }
        public bool HasProcesses { get { return job != IntPtr.Zero && JobPids().Count != 0; } }

        public LaunchSession(string path) { sessionsRoot = path; State = LaunchState.Exited; }

        public void Start(string executable, string arguments, string workingDirectory)
        {
            if (job != IntPtr.Zero)
            {
                try
                {
                    if (HasProcesses)
                    {
                        Cancel();
                        if (State != LaunchState.Cancelled) return;
                    }
                    var exiting = Stopwatch.StartNew();
                    // A job can report empty before its retained process handles signal exit.
                    while ((actual != null && !actual.HasExited) || (root != null && !root.HasExited) || HasProcesses)
                    {
                        if (exiting.ElapsedMilliseconds >= 2000)
                        {
                            Fail("上一轮渲染器仍在退出，请稍后重试。已有进程管理和日志已保留。 ");
                            return;
                        }
                        Thread.Sleep(20);
                    }
                }
                catch (Exception error)
                {
                    Fail("无法确认上一轮进程已退出，请稍后重试：" + error.Message);
                    return;
                }
            }
            Dispose();
            Id = Guid.NewGuid().ToString("N");
            DirectoryPath = Path.Combine(sessionsRoot, DateTime.Now.ToString("yyyyMMdd-HHmmss") + "-" + Id);
            Directory.CreateDirectory(DirectoryPath);
            StatusPath = Path.Combine(DirectoryPath, "status.json");
            LogPath = Path.Combine(DirectoryPath, "ue.log");
            State = LaunchState.Starting;
            Stage = "renderer";
            Detail = "正在启动渲染器";
            ActualPid = ExitCode = null;
            failure = null;
            nextLogCheck = 0;
            clock.Restart();
            Journal("launch", executable);
            try
            {
                if (!File.Exists(executable)) throw new FileNotFoundException("渲染器文件不存在", executable);
                arguments = arguments.Replace("{session}", Id).Replace("{status}", StatusPath).Replace("{log}", LogPath);
                job = Native.CreateJobObject(IntPtr.Zero, null);
                if (job == IntPtr.Zero) throw new Win32Exception();
                Native.STARTUPINFO startup = new Native.STARTUPINFO();
                startup.cb = Marshal.SizeOf(startup);
                // UE installs its cloak before ShowWindow; SW_HIDE here would suppress that first show event.
                Native.PROCESS_INFORMATION info;
                if (!Native.CreateProcess(executable, new StringBuilder(Quote(executable) + " " + arguments), IntPtr.Zero, IntPtr.Zero,
                    false, 0x4, IntPtr.Zero, workingDirectory, ref startup, out info)) throw new Win32Exception();
                try
                {
                    if (!Native.AssignProcessToJobObject(job, info.hProcess))
                    {
                        int error = Marshal.GetLastWin32Error();
                        Native.TerminateProcess(info.hProcess, 125);
                        throw new Win32Exception(error, "无法隔离本次渲染进程，已停止启动");
                    }
                    root = Process.GetProcessById((int)info.dwProcessId);
                    // Open and retain the handle now, so PID reuse never changes the process being observed.
                    IntPtr handle = root.Handle;
                    if (Native.ResumeThread(info.hThread) == UInt32.MaxValue) throw new Win32Exception();
                    Journal("root", root.Id.ToString());
                }
                finally { Native.CloseHandle(info.hThread); Native.CloseHandle(info.hProcess); }
            }
            catch (Exception error)
            {
                if (job != IntPtr.Zero) Native.TerminateJobObject(job, 125);
                Fail(error.Message);
            }
        }

        public void Poll()
        {
            if (Id == null || State == LaunchState.Cancelled) return;
            ReadStatus();
            ReadPublicationError();
            if (job == IntPtr.Zero || (actual != null ? !actual.HasExited : HasProcesses)) return;
            if (actual != null && actual.HasExited) ExitCode = actual.ExitCode;
            else if (root != null && root.HasExited) ExitCode = root.ExitCode;
            if (State == LaunchState.Duplicate) return;
            if (State == LaunchState.Ready)
            {
                State = LaunchState.Exited;
                Detail = "窗景已退出。" + ExitCodeLabel + "：" + CodeText();
                Journal("exit", Detail);
            }
            else if (State != LaunchState.Exited)
            {
                string message = failure ?? "渲染器在就绪前退出";
                string next = message + "。" + ExitCodeLabel + "：" + CodeText();
                if (Detail != next) { State = LaunchState.Failed; Detail = next; Journal("exit", Detail); }
            }
        }

        void ReadStatus()
        {
            if (State == LaunchState.Failed || State == LaunchState.Exited || State == LaunchState.Duplicate) return;
            if (!File.Exists(StatusPath)) return;
            try
            {
                if (new FileInfo(StatusPath).Length > 16384) return;
                Dictionary<string, object> data;
                using (var stream = new FileStream(StatusPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                using (var reader = new StreamReader(stream))
                    data = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(reader.ReadToEnd());
                if (data == null) return;
                object session, pid, stage, detail;
                if (!data.TryGetValue("session", out session) || !Id.Equals(session as string, StringComparison.Ordinal) ||
                    !data.TryGetValue("pid", out pid) || !data.TryGetValue("stage", out stage)) return;
                int processId = Convert.ToInt32(pid);
                string next = stage as string;
                if (Array.IndexOf(new[] { "renderer", "scene", "desktop", "ready", "error", "duplicate" }, next) < 0) return;
                // Corroborate the actual UE PID with our job, never a process name or an old log marker.
                if (!BindActual(processId)) return;
                string[] order = { "renderer", "scene", "desktop", "ready" };
                if (Array.IndexOf(order, next) >= 0 && Array.IndexOf(order, next) < Array.IndexOf(order, Stage)) return;
                if (next == Stage && State != LaunchState.Starting) return;
                Stage = next;
                Detail = data.TryGetValue("detail", out detail) ? Convert.ToString(detail) : "";
                if (next == "error") { Fail(Detail); return; }
                State = next == "ready" ? LaunchState.Ready : next == "duplicate" ? LaunchState.Duplicate : LaunchState.Loading;
                Journal(next, Detail);
            }
            catch (IOException) { } // Atomic publication can briefly race replacement or antivirus access.
            catch (UnauthorizedAccessException) { }
            catch (ArgumentException) { }
            catch (InvalidOperationException) { }
            catch (FormatException) { }
            catch (OverflowException) { }
            catch (Win32Exception) { }
        }

        bool BindActual(int processId)
        {
            if (actual != null) return ActualPid == processId;
            if (root != null && root.Id == processId) actual = root;
            else
            {
                Process candidate = Process.GetProcessById(processId);
                try
                {
                    bool owned;
                    if (!Native.IsProcessInJob(candidate.Handle, job, out owned) || !owned) return false;
                    actual = candidate;
                }
                finally { if (actual != candidate) candidate.Dispose(); }
            }
            ActualPid = processId;
            Journal("renderer-pid", processId.ToString());
            return true;
        }

        void ReadPublicationError()
        {
            // Only an explicit failure can come from this launch's log. Logs never establish readiness.
            if (!IsLoading || ElapsedSeconds < nextLogCheck || !File.Exists(LogPath)) return;
            nextLogCheck = ElapsedSeconds + 1;
            try
            {
                using (var stream = new FileStream(LogPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                {
                    bool tail = stream.Length > 65536;
                    if (tail) stream.Seek(-65536, SeekOrigin.End);
                    using (var reader = new StreamReader(stream))
                    {
                        if (tail) reader.ReadLine();
                        string line, prefix = "OOW_STARTUP_ERROR session=" + Id + " pid=";
                        while ((line = reader.ReadLine()) != null)
                        {
                            int start = line.IndexOf(prefix, StringComparison.Ordinal);
                            if (start < 0) continue;
                            start += prefix.Length;
                            int end = line.IndexOf(" detail=", start, StringComparison.Ordinal), pid;
                            if (end < 0 || !Int32.TryParse(line.Substring(start, end - start), out pid) || !BindActual(pid)) continue;
                            Fail(line.Substring(end + 8));
                            return;
                        }
                    }
                }
            }
            catch (IOException) { } catch (UnauthorizedAccessException) { }
            catch (ArgumentException) { } catch (InvalidOperationException) { } catch (Win32Exception) { }
        }

        public void Fail(string message)
        {
            failure = message;
            Detail = message;
            State = LaunchState.Failed;
            Journal("error", message);
        }

        public void Cancel()
        {
            if (job != IntPtr.Zero && !Native.TerminateJobObject(job, 1223))
            {
                Fail("取消失败：" + new Win32Exception().Message + "。可再次取消，日志已保留");
                return;
            }
            State = LaunchState.Cancelled;
            Detail = "已取消本次启动。已有窗景实例不受影响。";
            Journal("cancel", Detail);
        }

        public string CodeText() { return ExitCode.HasValue ? ExitCode.Value + " (0x" + unchecked((uint)ExitCode.Value).ToString("X8") + ")" : "尚未取得"; }
        void Journal(string kind, string text)
        {
            if (DirectoryPath != null) File.AppendAllText(Path.Combine(DirectoryPath, "launcher.log"),
                DateTime.UtcNow.ToString("o") + " " + kind + " " + text + Environment.NewLine, Encoding.UTF8);
        }

        List<int> JobPids()
        {
            int size = 8 + IntPtr.Size * 4096;
            IntPtr buffer = Marshal.AllocHGlobal(size);
            try
            {
                if (!Native.QueryInformationJobObject(job, 3, buffer, (uint)size, IntPtr.Zero)) throw new Win32Exception();
                int count = Marshal.ReadInt32(buffer, 4);
                var pids = new List<int>();
                for (int i = 0; i < count; ++i) pids.Add(Marshal.ReadIntPtr(buffer, 8 + i * IntPtr.Size).ToInt32());
                return pids;
            }
            finally { Marshal.FreeHGlobal(buffer); }
        }

        public static string Quote(string text)
        {
            // CommandLineToArgvW escaping, including a path ending in a backslash.
            var result = new StringBuilder("\"");
            int slashes = 0;
            foreach (char c in text)
            {
                if (c == '\\') { slashes++; continue; }
                result.Append('\\', c == '"' ? slashes * 2 + 1 : slashes);
                result.Append(c); slashes = 0;
            }
            result.Append('\\', slashes * 2).Append('"');
            return result.ToString();
        }

        public void Dispose()
        {
            if (actual != null && actual != root) actual.Dispose();
            if (root != null) root.Dispose();
            actual = root = null;
            if (job != IntPtr.Zero) Native.CloseHandle(job);
            job = IntPtr.Zero;
        }
    }

    internal static class Native
    {
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] internal struct STARTUPINFO
        {
            public int cb; public string lpReserved, lpDesktop, lpTitle;
            public uint dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
            public short wShowWindow, cbReserved2; public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
        }
        [StructLayout(LayoutKind.Sequential)] internal struct PROCESS_INFORMATION
        { public IntPtr hProcess, hThread; public uint dwProcessId, dwThreadId; }
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] internal static extern IntPtr CreateJobObject(IntPtr attributes, string name);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool IsProcessInJob(IntPtr process, IntPtr job, out bool result);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool QueryInformationJobObject(IntPtr job, int infoClass, IntPtr info, uint length, IntPtr returnLength);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] internal static extern bool CreateProcess(string app, StringBuilder command, IntPtr pa, IntPtr ta, bool inherit, uint flags, IntPtr environment, string directory, ref STARTUPINFO startup, out PROCESS_INFORMATION info);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern uint ResumeThread(IntPtr thread);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool TerminateJobObject(IntPtr job, uint code);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool TerminateProcess(IntPtr process, uint code);
        [DllImport("kernel32.dll")] internal static extern bool CloseHandle(IntPtr handle);
    }
}
