#if WITH_DEV_AUTOMATION_TESTS

#include "../WindowVisibilityButton.h"
#include "Misc/AutomationTest.h"
#include "Types/PaintArgs.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SWindow.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowVisibilityTest, "OutOfWindow.UI.SceneOnlyRecovery",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWindowVisibilityTest::RunTest(const FString& Parameters)
{
    if (!TestTrue(TEXT("Slate is available"), FSlateApplication::IsInitialized())) return false;
    FSlateApplication& App = FSlateApplication::Get();
    const TSharedPtr<SWindow> PreviousWindow = App.GetActiveTopLevelWindow();
    const TSharedPtr<SWidget> PreviousFocus = App.GetKeyboardFocusedWidget();
    const TSharedRef<SWindowVisibilityButton> Eye = SNew(SWindowVisibilityButton);
    const bool bOriginalScreenMessages = GAreScreenMessagesEnabled;
    const TSharedRef<SButton> OtherFocus = SNew(SButton);
    const TSharedRef<SWindow> Window = SNew(SWindow).ClientSize(FVector2D(96, 64))
        [SNew(SHorizontalBox)
            + SHorizontalBox::Slot()[Eye]
            + SHorizontalBox::Slot()[OtherFocus]];
    App.AddWindow(Window, false);
    Window->SlatePrepass();
    App.ProcessWindowActivatedEvent(FWindowActivateEvent(FWindowActivateEvent::EA_Activate, Window));

    const FGeometry Geometry = FGeometry::MakeRoot(FVector2D(32, 32), FSlateLayoutTransform());
    const FPointerEvent Pointer;
    auto DrawElementCount = [&]()
    {
        FSlateWindowElementList Elements(Window);
        const FPaintArgs Args(&Window.Get(), Window->GetHittestGrid(), FVector2D::ZeroVector, 0.0, 0.f);
        Eye->OnPaint(Args, Geometry, FSlateRect(0, 0, 32, 32), Elements, 0, FWidgetStyle(), true);
        int32 Count = 0;
        Elements.GetUncachedDrawElements().ApplyAfter([&](const auto&... Arrays) { ((Count += Arrays.Num()), ...); });
        return Count;
    };

    TestFalse(TEXT("UI starts visible"), Eye->IsInterfaceHidden());
    TestTrue(TEXT("Open eye draws"), DrawElementCount() > 0);
    Eye->OnMouseEnter(Geometry, Pointer);
    Eye->SimulateClick();
    TestTrue(TEXT("Click hides UI"), Eye->IsInterfaceHidden());
    TestFalse(TEXT("Scene-only mode also hides engine screen messages"), GAreScreenMessagesEnabled);
    TestFalse(TEXT("Eye disappears immediately under the cursor"), Eye->IsEyeVisible());
    TestEqual(TEXT("Hidden eye draws no elements"), DrawElementCount(), 0);

    Eye->OnMouseLeave(Pointer);
    Eye->OnMouseEnter(Geometry, Pointer);
    TestTrue(TEXT("Hover reveals eye while UI stays hidden"), Eye->IsEyeVisible() && Eye->IsInterfaceHidden());
    TestTrue(TEXT("Closed eye draws on hover"), DrawElementCount() > 0);
    Eye->OnMouseLeave(Pointer);
    TestEqual(TEXT("Leaving the hotspot removes all eye drawing"), DrawElementCount(), 0);
    Eye->OnMouseEnter(Geometry, Pointer);
    Eye->SimulateClick();
    TestFalse(TEXT("Clicking the closed eye restores UI"), Eye->IsInterfaceHidden());
    TestEqual(TEXT("Screen message setting is restored"), GAreScreenMessagesEnabled, bOriginalScreenMessages);
    TestTrue(TEXT("Restored eye remains visible"), Eye->IsEyeVisible());

    Eye->SimulateClick();
    TestTrue(TEXT("Focus moves to another control"), App.SetKeyboardFocus(OtherFocus));
    TestTrue(TEXT("Eye no longer owns keyboard focus"), App.GetKeyboardFocusedWidget() == OtherFocus);
    TestTrue(TEXT("Escape is handled by Slate's input processor"),
        App.ProcessKeyDownEvent(FKeyEvent(EKeys::Escape, FModifierKeysState(), 0, false, 0, 0)));
    TestFalse(TEXT("Escape restores UI despite different keyboard focus"), Eye->IsInterfaceHidden());
    TestTrue(TEXT("Escape restores eye drawing"), DrawElementCount() > 0);

    App.DestroyWindowImmediately(Window);
    if (PreviousWindow) App.ProcessWindowActivatedEvent(FWindowActivateEvent(FWindowActivateEvent::EA_Activate, PreviousWindow.ToSharedRef()));
    App.SetKeyboardFocus(PreviousFocus);
    return true;
}

#endif
