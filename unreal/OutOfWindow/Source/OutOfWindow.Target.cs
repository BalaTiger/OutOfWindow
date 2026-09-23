using UnrealBuildTool;
using System.Collections.Generic;
public class OutOfWindowTarget : TargetRules
{
    public OutOfWindowTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.V6;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_7;
        ExtraModuleNames.Add("OutOfWindow");
    }
}
