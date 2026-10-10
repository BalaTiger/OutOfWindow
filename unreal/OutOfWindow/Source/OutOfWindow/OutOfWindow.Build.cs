using UnrealBuildTool;
using System.IO;
public class OutOfWindow : ModuleRules
{
    public OutOfWindow(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.NoPCHs;
        // Read-only access to the renderer-created cloud parameters for test capture audits.
        PrivateIncludePaths.Add(Path.Combine(EngineDirectory, "Source", "Runtime", "Renderer", "Private"));
        PrivateIncludePaths.Add(Path.Combine(EngineDirectory, "Source", "Runtime", "Renderer", "Internal"));
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "InputCore", "Slate", "SlateCore", "ApplicationCore", "HTTP", "Json", "JsonUtilities", "RenderCore", "RHI", "Renderer", "ImageWriteQueue", "MeshDescription", "StaticMeshDescription" });
        if (Target.Platform == UnrealTargetPlatform.Win64)
            PublicSystemLibraries.AddRange(new[] { "user32.lib", "shell32.lib", "comctl32.lib" });
    }
}
