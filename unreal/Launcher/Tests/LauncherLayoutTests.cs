using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Reflection;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using OutOfWindow.Launcher;

// DrawToBitmap only. Never Show()/Run(), so the form's Shown handler cannot start UE.
internal static class LauncherLayoutTests
{
    const BindingFlags PrivateInstance = BindingFlags.Instance | BindingFlags.NonPublic;
    static List<object> Reports = new List<object>();
    static string Output;
    [STAThread]
    static int Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Output = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "layout", DateTime.UtcNow.ToString("yyyyMMdd-HHmmss"));
        Directory.CreateDirectory(Output);
        Capture("initial-100", "initial", 1f);
        Capture("slow-100", "slow", 1f);
        Capture("long-error-100", "error", 1f);
        Capture("duplicate-100", "duplicate", 1f);
        Capture("slow-200", "slow", 2f);
        Capture("long-error-200", "error", 2f);
        string report = Path.Combine(Output, "layout.json");
        File.WriteAllText(report, new JavaScriptSerializer().Serialize(new { note = "Offscreen WinForms control composite only. 200% cases scale geometry and fonts, not physical monitor DPI. No UE, desktop attachment, interactive GUI or monitor DPI validation.", reports = Reports }), new UTF8Encoding(false));
        Console.WriteLine("LAYOUT_RESULTS=" + report);
        return 0;
    }
    static T Field<T>(object item, string name) { return (T)item.GetType().GetField(name, PrivateInstance).GetValue(item); }
    static void Set(object item, string name, object value) { item.GetType().GetProperty(name).GetSetMethod(true).Invoke(item, new[] { value }); }
    static void Capture(string name, string state, float scale)
    {
        using (LauncherForm form = new LauncherForm(Output, "Alley"))
        {
            bool shown = false;
            form.Shown += delegate { shown = true; };
            LaunchSession session = Field<LaunchSession>(form, "session");
            string longError = "启动遇到问题：无法加载当前版本，因为渲染器模块与构建记录不一致。请重新运行 unreal\\Build-LoadingExperience.ps1，再点击重试。文件位置：C:\\Users\\这是一个很长的用户名\\Documents\\OutOfWindow\\unreal\\OutOfWindow\\Binaries\\Win64\\UnrealEditor-OutOfWindow.dll。请打开日志查看详细信息。";
            if (state == "error") session.Fail(longError);
            if (state == "duplicate") { Set(session, "State", LaunchState.Duplicate); Set(session, "Detail", "已有桌面场景正在运行，当前已有实例保持运行。"); }
            if (state == "slow")
            {
                Set(session, "State", LaunchState.Loading); Set(session, "Stage", "scene"); Set(session, "Detail", "场景和贴图仍在加载，完成准备后会显示桌面场景。");
                Stopwatch clock = Field<Stopwatch>(session, "clock");
                FieldInfo elapsed = typeof(Stopwatch).GetField("elapsed", PrivateInstance) ?? typeof(Stopwatch).GetField("_elapsed", PrivateInstance);
                if (elapsed == null) throw new Exception("Could not create slow-wait layout fixture.");
                elapsed.SetValue(clock, 31L * Stopwatch.Frequency);
            }
            if (state != "initial") typeof(LauncherForm).GetMethod("Render", PrivateInstance).Invoke(form, null);
            if (scale != 1f)
            {
                List<KeyValuePair<Control, Font>> explicitFonts = new List<KeyValuePair<Control, Font>>();
                foreach (Control control in form.Controls)
                    if (!control.Font.Equals(form.Font)) explicitFonts.Add(new KeyValuePair<Control, Font>(control, control.Font));
                form.Scale(new SizeF(scale, scale));
                form.Font = new Font(form.Font.FontFamily, form.Font.Size * scale, form.Font.Style);
                foreach (KeyValuePair<Control, Font> item in explicitFonts)
                    item.Key.Font = new Font(item.Value.FontFamily, item.Value.Size * scale, item.Value.Style);
            }
            form.CreateControl();
            using (Bitmap image = new Bitmap(form.Width, form.Height))
            {
                form.DrawToBitmap(image, new Rectangle(Point.Empty, image.Size));
                // Hidden parent controls are omitted by WM_PRINT; render each child offscreen.
                Point origin = form.PointToScreen(Point.Empty);
                origin.Offset(-form.Left, -form.Top);
                using (Graphics graphics = Graphics.FromImage(image))
                foreach (Control control in form.Controls)
                {
                    IntPtr handle = control.Handle;
                    using (Bitmap child = new Bitmap(control.Width, control.Height))
                    {
                        control.DrawToBitmap(child, new Rectangle(Point.Empty, child.Size));
                        graphics.DrawImageUnscaled(child, origin.X + control.Left, origin.Y + control.Top);
                    }
                }
                image.Save(Path.Combine(Output, name + ".png"), ImageFormat.Png);
            }
            if (shown) throw new Exception("Offscreen test unexpectedly showed the form.");
            Label subtitle = Field<Label>(form, "subtitle");
            Label elapsedLabel = Field<Label>(form, "elapsed");
            TextBox diagnostics = Field<TextBox>(form, "diagnostics");
            Size needed = TextRenderer.MeasureText(subtitle.Text, subtitle.Font, new Size(subtitle.Width, Int32.MaxValue), TextFormatFlags.WordBreak | TextFormatFlags.TextBoxControl);
            List<object> bounds = new List<object>();
            bool allInside = true;
            foreach (Control control in form.Controls)
            {
                bool inside = control.Left >= 0 && control.Top >= 0 && control.Right <= form.ClientSize.Width && control.Bottom <= form.ClientSize.Height;
                allInside &= inside;
                bounds.Add(new { type = control.GetType().Name, text = control.Text, x = control.Left, y = control.Top, width = control.Width, height = control.Height, inside = inside });
            }
            bool fullErrorAvailable = state != "error" || diagnostics.Text.Contains(longError) || needed.Height <= subtitle.Height;
            Reports.Add(new { name = name, scale = scale, shown = shown, clientWidth = form.ClientSize.Width, clientHeight = form.ClientSize.Height, allControlsInside = allInside, subtitleNeededHeight = needed.Height, subtitleHeight = subtitle.Height, fullErrorAvailable = fullErrorAvailable, elapsedText = elapsedLabel.Text, controls = bounds });
            Console.WriteLine(name + " inside=" + allInside + " fullErrorAvailable=" + fullErrorAvailable + " subtitleNeeded=" + needed.Height + "/" + subtitle.Height);
            if (!allInside || !fullErrorAvailable) throw new Exception("Layout check failed for " + name);
            session.Dispose();
        }
    }
}
