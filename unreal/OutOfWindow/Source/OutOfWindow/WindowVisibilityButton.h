#pragma once

#include "Framework/Application/IInputProcessor.h"
#include "Framework/Application/SlateApplication.h"
#include "InputCoreTypes.h"
#include "Brushes/SlateRoundedBoxBrush.h"
#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBox.h"

class SWindowVisibilityButton;

// Escape must work even after clicking the scene or moving focus off the button.
class FWindowUIInputProcessor : public IInputProcessor
{
public:
    explicit FWindowUIInputProcessor(TWeakPtr<SWindowVisibilityButton> InButton) : Button(InButton) {}
    virtual void Tick(float, FSlateApplication&, TSharedRef<ICursor>) override {}
    virtual bool HandleKeyDownEvent(FSlateApplication& App, const FKeyEvent& Event) override;
private:
    TWeakPtr<SWindowVisibilityButton> Button;
};

class SWindowVisibilityButton : public SButton
{
public:
    SLATE_BEGIN_ARGS(SWindowVisibilityButton) {} SLATE_END_ARGS()

    void Construct(const FArguments&)
    {
        SButton::Construct(SButton::FArguments()
            .ButtonStyle(FCoreStyle::Get(), "NoBorder")
            .ContentPadding(0)
            .AccessibleText_Lambda([this] { return FText::FromString(bInterfaceHidden ? TEXT("显示界面 (Esc)") : TEXT("隐藏界面")); })
            .OnClicked_Lambda([this] { SetInterfaceHidden(!bInterfaceHidden); return FReply::Handled(); })
            [SNew(SBox).WidthOverride(32).HeightOverride(32)]);
        InputProcessor = MakeShared<FWindowUIInputProcessor>(SharedThis(this));
        FSlateApplication::Get().RegisterInputPreProcessor(InputProcessor, 0);
    }

    virtual ~SWindowVisibilityButton() override
    {
        if (bInterfaceHidden) GAreScreenMessagesEnabled = bScreenMessagesBeforeHiding;
        if (FSlateApplication::IsInitialized()) FSlateApplication::Get().UnregisterInputPreProcessor(InputProcessor);
    }

    bool IsInterfaceHidden() const { return bInterfaceHidden; }
    bool IsEyeVisible() const { return !bInterfaceHidden || bPeek; }

    void SetInterfaceHidden(bool bHidden)
    {
        if (bInterfaceHidden == bHidden) return;
        if (bHidden) bScreenMessagesBeforeHiding = GAreScreenMessagesEnabled;
        GAreScreenMessagesEnabled = bHidden ? false : bScreenMessagesBeforeHiding;
        bInterfaceHidden = bHidden;
        // Clicking hides everything immediately, including the button under the cursor.
        bPeek = false;
        FSlateApplication::Get().DismissAllMenus();
        Invalidate(EInvalidateWidgetReason::Paint);
    }

    virtual void OnMouseEnter(const FGeometry& Geometry, const FPointerEvent& Event) override
    {
        SButton::OnMouseEnter(Geometry, Event);
        bPeek = bInterfaceHidden;
        Invalidate(EInvalidateWidgetReason::Paint);
    }

    virtual void OnMouseLeave(const FPointerEvent& Event) override
    {
        SButton::OnMouseLeave(Event);
        bPeek = false;
        Invalidate(EInvalidateWidgetReason::Paint);
    }

    virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& Geometry, const FSlateRect& CullRect,
        FSlateWindowElementList& Elements, int32 Layer, const FWidgetStyle& WidgetStyle, bool bEnabled) const override
    {
        // Remain hit-testable at the exact same position without drawing any pixels.
        if (!IsEyeVisible()) return Layer;
        static const FSlateRoundedBoxBrush Background(FLinearColor(.02f, .03f, .03f, .8f), 7.f);
        FSlateDrawElement::MakeBox(Elements, Layer, Geometry.ToPaintGeometry(), &Background, ESlateDrawEffect::None, Background.GetTint(WidgetStyle));
        Layer = SButton::OnPaint(Args, Geometry, CullRect, Elements, Layer, WidgetStyle, bEnabled);
        const FLinearColor Ink(.91f, .94f, .90f);
        const FVector2D Center = Geometry.GetLocalSize() * .5;
        auto Draw = [&](TArray<FVector2D> Points)
        {
            for (FVector2D& Point : Points) Point += Center;
            FSlateDrawElement::MakeLines(Elements, Layer + 1, Geometry.ToPaintGeometry(), Points, ESlateDrawEffect::None, Ink, true, 1.5f);
        };
        if (bInterfaceHidden)
        {
            Draw({ {-10, -2}, {-7, 1}, {-3, 3}, {3, 3}, {7, 1}, {10, -2} });
            Draw({ {-7, 1}, {-9, 5} });
            Draw({ {0, 3}, {0, 7} });
            Draw({ {7, 1}, {9, 5} });
        }
        else
        {
            Draw({ {-10, 0}, {-7, -4}, {-3, -6}, {3, -6}, {7, -4}, {10, 0}, {7, 4}, {3, 6}, {-3, 6}, {-7, 4}, {-10, 0} });
            TArray<FVector2D> Iris;
            for (int32 Index = 0; Index <= 16; ++Index)
            {
                const float Angle = Index * 2.f * PI / 16;
                Iris.Add(FVector2D(FMath::Cos(Angle), FMath::Sin(Angle)) * 2.5);
            }
            Draw(MoveTemp(Iris));
        }
        return Layer + 1;
    }

private:
    TSharedPtr<FWindowUIInputProcessor> InputProcessor;
    bool bInterfaceHidden = false;
    bool bPeek = false;
    bool bScreenMessagesBeforeHiding = false;
};

inline bool FWindowUIInputProcessor::HandleKeyDownEvent(FSlateApplication& App, const FKeyEvent& Event)
{
    const TSharedPtr<SWindowVisibilityButton> Pinned = Button.Pin();
    if (Event.GetKey() == EKeys::Escape && Pinned && Pinned->IsInterfaceHidden()
        && App.FindWidgetWindow(Pinned.ToSharedRef()) == App.GetActiveTopLevelWindow())
    {
        Pinned->SetInterfaceHidden(false);
        return true;
    }
    return false;
}
