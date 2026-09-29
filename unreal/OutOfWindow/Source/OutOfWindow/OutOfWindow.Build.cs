using UnrealBuildTool;
public class OutOfWindow : ModuleRules
{
    public OutOfWindow(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.NoPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "InputCore", "Slate", "SlateCore", "ApplicationCore", "HTTP", "Json", "JsonUtilities", "RenderCore", "RHI", "Renderer", "MeshDescription", "StaticMeshDescription" });
        if (Target.Platform == UnrealTargetPlatform.Win64)
            PublicSystemLibraries.AddRange(new[] { "user32.lib", "shell32.lib", "comctl32.lib" });
    }
}
