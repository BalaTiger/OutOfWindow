#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR

#include "../WindowMaterialLibrary.h"
#include "Materials/Material.h"
#include "Materials/MaterialExpressionConstant3Vector.h"
#include "Misc/AutomationTest.h"
#include "UObject/UObjectGlobals.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowMaterialTest, "OutOfWindow.Materials.ConnectedWorldPositionOffset",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWindowMaterialTest::RunTest(const FString& Parameters)
{
    TestFalse(TEXT("Null material is safe"),
        UWindowMaterialLibrary::EnableConnectedWorldPositionOffset(nullptr));

    UMaterial* Material = NewObject<UMaterial>();
    auto& Input = Material->GetEditorOnlyData()->WorldPositionOffset;
    Input.UseConstant = true;
    Input.Expression = nullptr;
    TestFalse(TEXT("Unconnected WPO is unchanged"),
        UWindowMaterialLibrary::EnableConnectedWorldPositionOffset(Material));
    TestTrue(TEXT("Unconnected WPO retains its constant mode"), Input.UseConstant != 0);

    UMaterialExpressionConstant3Vector* Expression = NewObject<UMaterialExpressionConstant3Vector>(Material);
    Input.Expression = Expression;
    TestTrue(TEXT("Imported constant mode is cleared when WPO has an expression"),
        UWindowMaterialLibrary::EnableConnectedWorldPositionOffset(Material));
    TestFalse(TEXT("Connected WPO no longer ignores its expression"), Input.UseConstant != 0);
    TestTrue(TEXT("The existing WPO expression is preserved"), Input.Expression == Expression);
    TestFalse(TEXT("Reapplying the repair makes no further change"),
        UWindowMaterialLibrary::EnableConnectedWorldPositionOffset(Material));
    TestFalse(TEXT("WPO remains enabled after the second call"), Input.UseConstant != 0);
    return true;
}

#endif
