using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using OutOfWindow.Launcher;

// Isolated manifest validation only: fake executable/module/map files are never run.
internal static class LauncherTargetTests
{
    static readonly List<object> Results = new List<object>();
    static string Output;
    static int Failures;

    [STAThread]
    static int Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Output = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "target-validation", DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        Directory.CreateDirectory(Output);
        Run("current-hashes-accepted", delegate(Fixture f) { Target target = Load(f); Assert(target.module == f.Module, "Accepted target changed module path."); return "matching module/source SHA256 and existing map accepted"; });
        Run("missing-manifest-rejected", delegate(Fixture f) { File.Delete(f.Manifest); Exception error = Rejected(f); Assert(error.Message.Contains("Build-LoadingExperience.ps1"), "Missing manifest recovery instruction lost."); return "missing manifest rejected with build instruction"; });
        Run("missing-module-rejected", delegate(Fixture f) { File.Delete(f.Module); AssertMissing(f, f.Module); return "missing module rejected with exact missing file"; });
        Run("missing-map-rejected", delegate(Fixture f) { File.Delete(f.Map); AssertMissing(f, f.Map); return "missing Alley.umap rejected with exact missing file"; });
        Run("changed-source-rejected", delegate(Fixture f) { File.AppendAllText(f.Source, "\nchanged"); Exception error = Rejected(f); Assert(error.Message.Contains(f.Target.sources[0].path), "Changed source path not reported."); return "source hash mismatch rejected"; });
        Run("changed-module-rejected", delegate(Fixture f) { File.AppendAllText(f.Module, "changed"); Exception error = Rejected(f); Assert(error.Message.Contains("UE") && error.Message.Contains("重新构建"), "Module mismatch recovery instruction lost."); return "module hash mismatch rejected"; });
        Run("missing-executable-rejected", delegate(Fixture f) { File.Delete(f.Executable); AssertMissing(f, f.Executable); return "missing executable rejected"; });
        Run("added-source-rejected", delegate(Fixture f) { string added = Path.Combine(f.Root, "Source", "NewFeature.cpp"); File.WriteAllText(added, "// new source"); Exception error = Rejected(f); Assert(error.Message.Contains(added), "New source path not reported."); return "new source absent from build manifest rejected"; });
        Run("added-config-rejected", delegate(Fixture f) { string directory = Path.Combine(f.Root, "Config"); Directory.CreateDirectory(directory); string added = Path.Combine(directory, "NewSettings.ini"); File.WriteAllText(added, "[Fixture]"); Exception error = Rejected(f); Assert(error.Message.Contains(added), "New config path not reported."); return "new Config directory/file absent from build manifest rejected"; });
        Run("restored-source-recovers", delegate(Fixture f) { byte[] original = File.ReadAllBytes(f.Source); File.AppendAllText(f.Source, "changed"); Rejected(f); File.WriteAllBytes(f.Source, original); Load(f); return "source mismatch rejected; restoring exact original hash accepted"; });
        Run("default-state-directory-compatible", delegate(Fixture f) { Load(f); Load(f, Path.Combine(f.Root, ".runtime", "launcher")); return "omitted and explicit default state directory both accept the same manifest"; });
        Run("custom-state-directory-used", delegate(Fixture f) { string state = Path.Combine(f.Root, ".runtime", "candidate output"); f.WriteManifest(state); File.Delete(f.Manifest); Load(f, state); Rejected(f); return "custom state manifest accepted without a default manifest; default lookup remains independent"; });
        Run("state-directories-do-not-share-manifests", delegate(Fixture f) { string first = Path.Combine(f.Root, ".runtime", "first"), second = Path.Combine(f.Root, ".runtime", "second"); f.WriteManifest(first); f.Target.moduleSha256 = "invalid"; f.WriteManifest(second); Load(f, first); Exception error = Rejected(f, second); Assert(error.Message.Contains("UE"), "Second directory did not use its own invalid module hash."); Load(f); return "valid first/default manifests accepted; invalid second manifest independently rejected"; });
        Run("custom-missing-manifest-no-fallback", delegate(Fixture f) { Rejected(f, Path.Combine(f.Root, ".runtime", "missing-state")); Load(f); return "missing custom manifest rejected despite valid default manifest"; });
        Run("custom-session-and-error-paths-isolated", CustomStatePaths);
        Run("state-directory-outside-root-rejected", delegate(Fixture f) { AssertStateRejected(f, Path.Combine(f.Root, "..", "outside-state")); AssertStateRejected(f, f.Root + "-sibling"); return "normalized traversal and root-prefix sibling paths rejected"; });
        string report = Path.Combine(Output, "results.json");
        File.WriteAllText(report, new JavaScriptSerializer().Serialize(new { failures = Failures, tests = Results, note = "Reflection invokes LoadTarget only. Forms never shown; no UE executable, map, or module loaded." }), new UTF8Encoding(false));
        Console.WriteLine("TARGET_RESULTS=" + report);
        Console.WriteLine("TARGET_TESTS=" + Results.Count + " FAILURES=" + Failures);
        return Failures == 0 ? 0 : 1;
    }

    static void Run(string name, Func<Fixture, string> test)
    {
        try { string evidence = test(new Fixture(Path.Combine(Output, name))); Results.Add(new { name = name, passed = true, evidence = evidence }); Console.WriteLine("PASS " + name + " " + evidence); }
        catch (Exception error) { Failures++; Results.Add(new { name = name, passed = false, evidence = error.ToString() }); Console.WriteLine("FAIL " + name + " " + error.Message); }
    }

    static Target Load(Fixture fixture, string stateDirectory = null)
    {
        using (LauncherForm form = new LauncherForm(fixture.Root, "Alley", stateDirectory))
        {
            bool shown = false;
            form.Shown += delegate { shown = true; };
            try
            {
                Target target = (Target)typeof(LauncherForm).GetMethod("LoadTarget", BindingFlags.Instance | BindingFlags.NonPublic).Invoke(form, null);
                Assert(!shown, "Unexpectedly showed form.");
                return target;
            }
            catch (TargetInvocationException error) { throw error.InnerException ?? error; }
            finally { ((LaunchSession)typeof(LauncherForm).GetField("session", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(form)).Dispose(); }
        }
    }

    static Exception Rejected(Fixture fixture, string stateDirectory = null)
    {
        try { Load(fixture, stateDirectory); }
        catch (Exception error) { return error; }
        throw new Exception("Invalid fixture was accepted.");
    }

    static void AssertMissing(Fixture fixture, string path)
    {
        FileNotFoundException error = Rejected(fixture) as FileNotFoundException;
        Assert(error != null && error.FileName == path, "Expected missing file " + path);
    }

    static void Assert(bool condition, string message) { if (!condition) throw new Exception(message); }

    static void AssertStateRejected(Fixture fixture, string stateDirectory)
    {
        Exception error = Rejected(fixture, stateDirectory);
        Assert(error is ArgumentException, "Outside state directory was not rejected during construction.");
        Assert(!Directory.Exists(Path.GetFullPath(stateDirectory)), "Rejected state directory was unexpectedly created.");
    }

    static string CustomStatePaths(Fixture fixture)
    {
        string state = Path.Combine(fixture.Root, ".runtime", "isolated-state");
        using (LauncherForm form = new LauncherForm(fixture.Root, "Alley", state))
        {
            bool shown = false;
            form.Shown += delegate { shown = true; };
            LaunchSession session = (LaunchSession)typeof(LauncherForm).GetField("session", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(form);
            try
            {
                MethodInfo showError = typeof(LauncherForm).GetMethod("ShowError", BindingFlags.Instance | BindingFlags.NonPublic);
                showError.Invoke(form, new object[] { new Exception("Isolated preparation error fixture.") });
                Assert(File.Exists(Path.Combine(state, "launcher-errors.log")), "Preparation error did not use custom state path.");
                session.Start(Path.Combine(fixture.Root, "missing-executable.exe"), "", fixture.Root);
                Assert(session.DirectoryPath.StartsWith(Path.Combine(state, "sessions") + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase), "Session escaped custom state directory.");
                Assert(File.Exists(Path.Combine(session.DirectoryPath, "launcher.log")), "Session journal missing from custom state directory.");
                showError.Invoke(form, new object[] { new Exception("Isolated active-session error fixture.") });
                Assert(File.Exists(Path.Combine(session.DirectoryPath, "launcher-errors.log")), "Active error did not use custom session path.");
                Assert(!Directory.Exists(Path.Combine(fixture.Root, ".runtime", "launcher", "sessions")), "Default state directory received custom session output.");
                Assert(!File.Exists(Path.Combine(fixture.Root, ".runtime", "launcher", "launcher-errors.log")), "Default directory received custom preparation error.");
                Assert(!shown, "State-path test unexpectedly showed form.");
                return "preparation errors, sessions and session errors stay inside explicit state directory; default unchanged";
            }
            finally { session.Dispose(); }
        }
    }

    internal sealed class Fixture
    {
        public readonly string Root, Executable, Module, Map, Source, Manifest;
        public readonly Target Target;
        public Fixture(string root)
        {
            Root = root;
            Directory.CreateDirectory(root);
            Executable = Path.Combine(root, "FakeRenderer.exe");
            Module = Path.Combine(root, "FakeRenderer.dll");
            Source = Path.Combine(root, "Source", "Fixture.cpp");
            Map = Path.Combine(root, "Content", "Maps", "Alley.umap");
            Manifest = Path.Combine(root, ".runtime", "launcher", "target.json");
            string project = Path.Combine(root, "FakeProject.uproject");
            Directory.CreateDirectory(Path.GetDirectoryName(Source));
            Directory.CreateDirectory(Path.GetDirectoryName(Map));
            Directory.CreateDirectory(Path.GetDirectoryName(Manifest));
            File.WriteAllText(Executable, "FAKE. Never executable.");
            File.WriteAllText(Module, "FAKE. Never loaded.");
            File.WriteAllText(Source, "// fixture source");
            File.WriteAllText(project, "{}");
            File.WriteAllBytes(Map, new byte[0]);
            Target = new Target { executable = Executable, project = project, module = Module, moduleSha256 = Hash(Module), builtUtc = DateTime.UtcNow.ToString("o"), sources = new List<SourceHash> { new SourceHash { path = "Source\\Fixture.cpp", sha256 = Hash(Source) }, new SourceHash { path = "FakeProject.uproject", sha256 = Hash(project) } } };
            File.WriteAllText(Manifest, new JavaScriptSerializer().Serialize(Target), new UTF8Encoding(false));
        }
        public void WriteManifest(string stateDirectory)
        {
            Directory.CreateDirectory(stateDirectory);
            File.WriteAllText(Path.Combine(stateDirectory, "target.json"), new JavaScriptSerializer().Serialize(Target), new UTF8Encoding(false));
        }
        static string Hash(string path)
        {
            using (FileStream stream = File.OpenRead(path))
            using (SHA256 sha = SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "");
        }
    }
}
