using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace OutOfWindow.Launcher
{
    internal static class Program
    {
        public const string WindowTitle = "Out of Window · 启动器";
        [STAThread] static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            string root = null, scene = "Alley", stateDirectory = null;
            foreach (string arg in args)
            {
                if (arg.StartsWith("--root=")) root = arg.Substring(7);
                if (arg.StartsWith("--scene=")) scene = arg.Substring(8);
                if (arg.StartsWith("--state-dir=")) stateDirectory = arg.Substring(12);
            }
            if (String.IsNullOrEmpty(root)) root = Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "..", ".."));
            bool created;
            using (var mutex = new Mutex(true, "Local\\OutOfWindow.Launcher.v1", out created))
            {
                if (!created)
                {
                    IntPtr window = FindWindow(null, WindowTitle);
                    if (window != IntPtr.Zero) { ShowWindow(window, 9); SetForegroundWindow(window); }
                    else MessageBox.Show("启动器已在运行，请从任务栏打开。", WindowTitle);
                    return;
                }
                try { Application.Run(new LauncherForm(root, scene, stateDirectory)); }
                catch (Exception error) { MessageBox.Show(error.Message, WindowTitle, MessageBoxButtons.OK, MessageBoxIcon.Error); }
            }
        }
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr FindWindow(string type, string title);
        [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr window, int command);
        [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr window);
    }

    internal sealed class Target
    {
        public string executable { get; set; }
        public string project { get; set; }
        public string module { get; set; }
        public string moduleSha256 { get; set; }
        public string builtUtc { get; set; }
        public List<SourceHash> sources { get; set; }
    }
    internal sealed class SourceHash { public string path { get; set; } public string sha256 { get; set; } }

    internal sealed class LauncherForm : Form
    {
        readonly string root, scene, stateDirectory;
        readonly LaunchSession session;
        readonly Label stage = new Label(), subtitle = new Label(), elapsed = new Label();
        readonly TextBox diagnostics = new TextBox();
        readonly Button cancel = new Button(), retry = new Button(), logs = new Button(), close = new Button();
        readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
        string targetDescription = "", preparationError;
        bool preparing, closing;

        public LauncherForm(string rootPath, string sceneName, string statePath = null)
        {
            root = Path.GetFullPath(rootPath);
            scene = sceneName;
            stateDirectory = Path.GetFullPath(statePath ?? Path.Combine(root, ".runtime", "launcher"));
            if (!stateDirectory.StartsWith(root.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("启动记录目录必须位于当前项目内。");
            session = new LaunchSession(Path.Combine(stateDirectory, "sessions"));
            Text = Program.WindowTitle;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(620, 410);
            MinimumSize = new Size(636, 449);
            Font = new Font("Microsoft YaHei UI", 10);
            BackColor = Color.FromArgb(246, 248, 250);
            var heading = new Label { Text = "OUT OF WINDOW", Location = new Point(24, 21), Size = new Size(560, 26), Font = new Font(Font.FontFamily, 11, FontStyle.Bold), ForeColor = Color.FromArgb(50, 70, 82) };
            stage.SetBounds(24, 66, 560, 38);
            stage.Font = new Font(Font.FontFamily, 21, FontStyle.Bold);
            stage.Text = "启动渲染器";
            subtitle.SetBounds(26, 114, 568, 51);
            subtitle.AutoEllipsis = true;
            subtitle.Text = "正在核对当前版本…";
            elapsed.SetBounds(26, 173, 560, 24);
            elapsed.ForeColor = Color.FromArgb(80, 95, 105);
            diagnostics.SetBounds(26, 211, 568, 120);
            diagnostics.Multiline = true; diagnostics.ReadOnly = true; diagnostics.ScrollBars = ScrollBars.Vertical;
            diagnostics.BackColor = Color.White; diagnostics.BorderStyle = BorderStyle.FixedSingle;
            diagnostics.Anchor = AnchorStyles.Left | AnchorStyles.Top | AnchorStyles.Right | AnchorStyles.Bottom;
            cancel.Text = "取消启动"; retry.Text = "重试"; logs.Text = "打开日志"; close.Text = "关闭启动器";
            var buttons = new[] { cancel, retry, logs, close };
            for (int i = 0; i < buttons.Length; ++i)
            {
                buttons[i].SetBounds(26 + i * 146, 354, 130, 33);
                buttons[i].Anchor = AnchorStyles.Left | AnchorStyles.Bottom;
            }
            Controls.AddRange(new Control[] { heading, stage, subtitle, elapsed, diagnostics, cancel, retry, logs, close });
            cancel.Click += delegate { try { session.Cancel(); } catch (Exception e) { ShowError(e); } Render(); };
            retry.Click += delegate { BeginLaunch(); };
            logs.Click += delegate
            {
                try
                {
                    string path = session.DirectoryPath ?? stateDirectory;
                    Directory.CreateDirectory(path);
                    Process.Start(new ProcessStartInfo("explorer.exe", LaunchSession.Quote(path)) { UseShellExecute = true });
                }
                catch (Exception e) { MessageBox.Show(this, e.Message, "无法打开日志目录"); }
            };
            close.Click += delegate { Close(); };
            FormClosing += delegate(object sender, FormClosingEventArgs e)
            {
                if (preparing) { closing = true; return; }
                if (session.IsLoading)
                {
                    try { session.Cancel(); } catch (Exception error) { ShowError(error); e.Cancel = true; }
                    if (session.State != LaunchState.Cancelled) e.Cancel = true;
                }
            };
            FormClosed += delegate { timer.Stop(); session.Dispose(); };
            timer.Interval = 250;
            timer.Tick += delegate { try { session.Poll(); } catch (Exception e) { ShowError(e); } Render(); };
            Shown += delegate { BeginLaunch(); timer.Start(); };
        }

        void BeginLaunch()
        {
            if (preparing) return;
            preparing = true;
            preparationError = null;
            stage.Text = "启动渲染器";
            subtitle.Text = "正在核对当前版本…";
            cancel.Enabled = retry.Enabled = false;
            ThreadPool.QueueUserWorkItem(delegate
            {
                Target target = null; Exception problem = null;
                try { target = LoadTarget(); } catch (Exception e) { problem = e; }
                if (closing || IsDisposed) return;
                try
                {
                    BeginInvoke((Action)delegate
                    {
                        preparing = false;
                        if (problem != null) ShowError(problem);
                        else
                        {
                            targetDescription = "构建：" + target.builtUtc + "\r\n引擎：" + target.executable + "\r\n工程：" + target.project;
                            string arguments = LaunchSession.Quote(target.project) + " /Game/Maps/" + scene +
                                " -game -windowed -ResX=1280 -ResY=820 -NoSplash -NoLoadingScreen -unattended" +
                                " -OOWLaunchId={session} -OOWLaunchStatus=\"{status}\" -abslog=\"{log}\"";
                            try { session.Start(target.executable, arguments, Path.GetDirectoryName(target.project)); }
                            catch (Exception e) { ShowError(e); }
                        }
                        Render();
                    });
                }
                catch (InvalidOperationException) { }
            });
        }

        Target LoadTarget()
        {
            if (Array.IndexOf(new[] { "Alley", "City", "Village", "Forest", "Coast" }, scene) < 0) throw new Exception("未知场景：" + scene);
            string manifest = Path.Combine(stateDirectory, "target.json");
            if (!File.Exists(manifest)) throw new Exception("尚未构建支持加载反馈的版本。请运行 unreal\\Build-LoadingExperience.ps1，再点击重试。");
            var target = new JavaScriptSerializer().Deserialize<Target>(File.ReadAllText(manifest));
            if (target == null || target.sources == null || target.sources.Count == 0) throw new Exception("启动配置不完整，请重新构建。");
            foreach (string file in new[] { target.executable, target.project, target.module })
                if (String.IsNullOrEmpty(file) || !File.Exists(file)) throw new FileNotFoundException("构建文件不存在，请重新构建", file);
            if (!Hash(target.module).Equals(target.moduleSha256, StringComparison.OrdinalIgnoreCase))
                throw new Exception("UE 模块与启动记录不一致，请重新构建；没有启动旧包。");
            var recorded = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var source in target.sources)
            {
                string path = Path.GetFullPath(Path.Combine(root, source.path));
                if (!path.StartsWith(root.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                    throw new Exception("构建源文件路径无效。");
                if (!File.Exists(path) || !Hash(path).Equals(source.sha256, StringComparison.OrdinalIgnoreCase))
                    throw new Exception("源码已变化，需要重新构建：" + source.path);
                recorded.Add(path);
            }
            foreach (string path in recorded)
                if (path.EndsWith(".uproject", StringComparison.OrdinalIgnoreCase))
                    foreach (string folder in new[] { "Source", "Config" })
                    {
                        string directory = Path.Combine(Path.GetDirectoryName(path), folder);
                        if (!Directory.Exists(directory)) continue;
                        foreach (string file in Directory.GetFiles(directory, "*", SearchOption.AllDirectories))
                            if (!recorded.Contains(Path.GetFullPath(file))) throw new Exception("新增源码尚未构建：" + file);
                    }
            string map = Path.Combine(Path.GetDirectoryName(target.project), "Content", "Maps", scene + ".umap");
            if (!File.Exists(map)) throw new FileNotFoundException("场景文件不存在", map);
            return target;
        }

        static string Hash(string file)
        {
            using (var stream = File.OpenRead(file)) using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "");
        }

        void ShowError(Exception error)
        {
            preparationError = error.Message;
            string directory = session.DirectoryPath ?? stateDirectory;
            try { Directory.CreateDirectory(directory); File.AppendAllText(Path.Combine(directory, "launcher-errors.log"), DateTime.UtcNow.ToString("o") + " " + error + Environment.NewLine); }
            catch (IOException) { } catch (UnauthorizedAccessException) { }
        }

        void Render()
        {
            if (preparing) return;
            if (preparationError != null) { stage.Text = "启动遇到问题"; subtitle.Text = "本次启动未完成。完整错误已保留在下方，可打开日志或重试。"; }
            else
            {
                switch (session.State)
                {
                    case LaunchState.Ready: stage.Text = "就绪"; break;
                    case LaunchState.Failed: stage.Text = "启动遇到问题"; break;
                    case LaunchState.Exited: stage.Text = "窗景已退出"; break;
                    case LaunchState.Cancelled: stage.Text = "已取消"; break;
                    case LaunchState.Duplicate: stage.Text = "已有窗景正在运行"; break;
                    default: stage.Text = session.Stage == "scene" ? "加载场景" : session.Stage == "desktop" ? "连接桌面" : "启动渲染器"; break;
                }
                subtitle.Text = session.State == LaunchState.Failed ? "本次启动未完成。完整错误与退出码已保留在下方，可打开日志或重试。" : session.Detail;
            }
            elapsed.Text = session.IsLoading && session.ElapsedSeconds >= 30
                ? "仍在加载 · 已等待 " + (int)session.ElapsedSeconds + " 秒。首次加载可能较久，可随时取消。"
                : session.IsLoading ? "已等待 " + (int)session.ElapsedSeconds + " 秒" : "日志和退出信息会保留在这里。";
            diagnostics.Text = "详情：" + (preparationError ?? session.Detail) + "\r\n" + targetDescription + (session.ActualPid.HasValue ? "\r\nUE 进程：" + session.ActualPid : "") +
                (session.ExitCode.HasValue ? "\r\n" + session.ExitCodeLabel + "：" + session.CodeText() : "") +
                "\r\n日志：" + (session.DirectoryPath ?? stateDirectory);
            cancel.Enabled = session.CanCancel;
            cancel.Text = session.State == LaunchState.Failed ? "取消本次进程" : "取消启动";
            retry.Enabled = !session.IsLoading || preparationError != null;
            if (session.State == LaunchState.Ready && preparationError == null) retry.Enabled = false;
            close.Text = session.IsLoading && preparationError == null ? "取消并关闭" : "关闭启动器";
        }
    }
}
