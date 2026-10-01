#if WITH_DEV_AUTOMATION_TESTS

#include "../WindowFrameLighting.h"
#include "Components/PointLightComponent.h"
#include "Components/RectLightComponent.h"
#include "Components/SpotLightComponent.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Misc/AutomationTest.h"
#include "Misc/ScopeExit.h"
#include <limits>

namespace
{
// Deliberately leave the components unregistered: these tests exercise ownership,
// selection and state restoration without creating rendering resources or assets.
template <class T>
T* MakeFrameTestLight(UWorld* World, const FVector& Location, float Radius, bool bInterior = false)
{
    AActor* Owner = World->SpawnActor<AActor>();
    if (!Owner) return nullptr;
    Owner->Tags.Add(TEXT("OOWNightLight"));
    if (bInterior) Owner->Tags.Add(TEXT("OOWInteriorLight"));
    T* Light = NewObject<T>(Owner);
    Owner->AddInstanceComponent(Light);
    Owner->SetRootComponent(Light);
    Light->SetMobility(EComponentMobility::Movable);
    Light->SetRelativeLocation(Location);
    Light->SetAttenuationRadius(Radius);
    Light->SetCastShadows(true);
    Light->CastDynamicShadows = true;
    Light->SetLightingChannels(true, false, false);
    return Light;
}

UPointLightComponent* MakePoint(UWorld* World, const FVector& Location, float Radius, bool bInterior = false)
{
    UPointLightComponent* Light = MakeFrameTestLight<UPointLightComponent>(World, Location, Radius, bInterior);
    if (Light) Light->SetSourceRadius(8.f);
    return Light;
}

const FBox TestFrame(FVector(89, -50, -30), FVector(98, 50, 30));
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowFrameLightSelectionTest, "OutOfWindow.Frame.ShadowLightSelection",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWindowFrameLightSelectionTest::RunTest(const FString& Parameters)
{
    UWorld* World = UWorld::CreateWorld(EWorldType::Game, false);
    if (!TestNotNull(TEXT("Test world"), World)) return false;
    ON_SCOPE_EXIT { World->DestroyWorld(false); };
    // These two lights reproduce the diagnosed camera-local street-lamp distances.
    UPointLightComponent* Nearest = MakePoint(World, FVector(161, 457, -908), 1600);
    UPointLightComponent* Farther = MakePoint(World, FVector(-198, -852, -907), 1600);
    UPointLightComponent* Interior = MakePoint(World, FVector(95, 0, 0), 1600, true);
    // This sphere covers the camera but not any part of the foreground frame.
    UPointLightComponent* MissesFrame = MakePoint(World, FVector::ZeroVector, 20);
    USpotLightComponent* Spot = MakeFrameTestLight<USpotLightComponent>(World, FVector(10, 0, 0), 1600);
    UPointLightComponent* WrongChannel = MakePoint(World, FVector(20, 0, 0), 1600);
    UPointLightComponent* Unshadowed = MakePoint(World, FVector(25, 0, 0), 1600);
    UPointLightComponent* Malformed = MakePoint(World, FVector(30, 0, 0), 1600);
    if (!TestNotNull(TEXT("Nearest source"), Nearest) || !TestNotNull(TEXT("Farther source"), Farther)
        || !TestNotNull(TEXT("Interior source"), Interior) || !TestNotNull(TEXT("Missed sphere"), MissesFrame)
        || !TestNotNull(TEXT("Spot source"), Spot) || !TestNotNull(TEXT("Other channel"), WrongChannel)
        || !TestNotNull(TEXT("Unshadowed source"), Unshadowed) || !TestNotNull(TEXT("Malformed source"), Malformed)) return false;
    Spot->SetSourceRadius(8);
    WrongChannel->SetLightingChannels(false, true, false);
    Unshadowed->SetCastShadows(false);
    Malformed->AttenuationRadius = std::numeric_limits<float>::quiet_NaN();

    TArray<TObjectPtr<ULightComponent>> Lights{Interior, Farther, Spot, MissesFrame, Nearest, WrongChannel, Unshadowed, Malformed, Nearest, nullptr};
    const auto First = FWindowFrameLighting::SelectExteriorLights(TEXT("Alley"), FVector::ZeroVector, TestFrame, Lights);
    if (!TestEqual(TEXT("Only one diagnosed exterior source receives the softening budget"), First.Num(), 1)) return false;
    TestTrue(TEXT("Near interiors, spots, wrong channels, missed spheres and duplicates cannot consume the budget"), First[0] == Nearest);
    TArray<TObjectPtr<ULightComponent>> Reordered{Nearest, Malformed, Unshadowed, WrongChannel, MissesFrame, Spot, Farther, Interior};
    const auto Second = FWindowFrameLighting::SelectExteriorLights(TEXT("Alley"), FVector::ZeroVector, TestFrame, Reordered);
    TestTrue(TEXT("Actor discovery order does not change the selected source"), Second.Num() == 1 && Second[0] == Nearest);
    TestEqual(TEXT("City is outside this Alley-specific diagnosis"),
        FWindowFrameLighting::SelectExteriorLights(TEXT("City"), FVector::ZeroVector, TestFrame, Lights).Num(), 0);
    TestEqual(TEXT("Unavailable frame geometry produces no broad fallback selection"),
        FWindowFrameLighting::SelectExteriorLights(TEXT("Alley"), FVector::ZeroVector, FBox(ForceInit), Lights).Num(), 0);
    const FVector InvalidCamera(std::numeric_limits<double>::quiet_NaN(), 0, 0);
    TestEqual(TEXT("Invalid camera data cannot select lights"),
        FWindowFrameLighting::SelectExteriorLights(TEXT("Alley"), InvalidCamera, TestFrame, Lights).Num(), 0);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowFrameLightQualityTest, "OutOfWindow.Frame.ShadowQualityFallbackAndRestore",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWindowFrameLightQualityTest::RunTest(const FString& Parameters)
{
    UWorld* World = UWorld::CreateWorld(EWorldType::Game, false);
    if (!TestNotNull(TEXT("Test world"), World)) return false;
    ON_SCOPE_EXIT { World->DestroyWorld(false); };
    UPointLightComponent* Exterior = MakePoint(World, FVector(500, 0, 0), 1600);
    UPointLightComponent* Other = MakePoint(World, FVector(1000, 0, 0), 1600);
    URectLightComponent* Indoor = MakeFrameTestLight<URectLightComponent>(World, FVector(-250, -90, 110), 600, true);
    if (!TestNotNull(TEXT("Exterior source"), Exterior) || !TestNotNull(TEXT("Untouched source"), Other)
        || !TestNotNull(TEXT("Indoor rect"), Indoor)) return false;
    Exterior->SetCastRaytracedShadows(ECastRayTracedShadow::UseProjectSetting);
    Exterior->SetSamplesPerPixel(7);
    Exterior->SetIntensity(2500);
    Exterior->SetShadowBias(.31f);
    Exterior->SetUseTemperature(true);
    Exterior->SetTemperature(3100);
    Indoor->SetCastRaytracedShadows(ECastRayTracedShadow::Disabled);
    Indoor->SetSamplesPerPixel(3);
    Indoor->SetSourceWidth(120);
    Indoor->SetSourceHeight(70);
    const auto OtherMode = Other->CastRaytracedShadow;
    const int32 OtherSamples = Other->SamplesPerPixel;
    Other->SetSourceRadius(50);
    const FVector ExteriorLocation = Exterior->GetComponentLocation();
    TArray<TObjectPtr<ULightComponent>> Lights{Other, Exterior};
    FWindowFrameLighting Policy;
    auto Apply = [&](int32 Quality, bool bHardware) { Policy.Update(TEXT("Alley"), FVector::ZeroVector, TestFrame, Lights, Indoor, Quality, bHardware); };

    Apply(1, true);
    TestEqual(TEXT("One street lamp and the explicit local rect are managed"), Policy.GetManagedLightCount(), 2);
    TestTrue(TEXT("The selected exterior source explicitly retains VSM"), Exterior->CastRaytracedShadow == ECastRayTracedShadow::Disabled);
    TestEqual(TEXT("A small authored source gains a finite 24 cm radius"), Exterior->SourceRadius, 24.f);
    TestTrue(TEXT("The optional indoor source explicitly uses RT"), Indoor->CastRaytracedShadow == ECastRayTracedShadow::Enabled);
    TestEqual(TEXT("Exterior SPP remains authored because it does not use RT"), Exterior->SamplesPerPixel, 7);
    TestEqual(TEXT("Quality 1 bounds indoor samples"), Indoor->SamplesPerPixel, 2);
    Apply(2, true);
    Apply(2, true); // Repeated updates must not capture an already-overridden state as the original.
    TestEqual(TEXT("High quality never changes the exterior SPP"), Exterior->SamplesPerPixel, 7);
    TestTrue(TEXT("High quality does not switch the exterior source to RT"), Exterior->CastRaytracedShadow == ECastRayTracedShadow::Disabled);
    TestEqual(TEXT("Quality changes do not resize the exterior emitter"), Exterior->SourceRadius, 24.f);
    TestEqual(TEXT("Quality 2 raises the indoor samples"), Indoor->SamplesPerPixel, 4);
    Apply(0, true);
    TestTrue(TEXT("Low quality explicitly returns to VSM even on RT hardware"), Exterior->CastRaytracedShadow == ECastRayTracedShadow::Disabled);
    TestTrue(TEXT("Low quality also returns the indoor source to VSM"), Indoor->CastRaytracedShadow == ECastRayTracedShadow::Disabled);
    TestEqual(TEXT("VSM does not retain an unnecessary RT sample override"), Exterior->SamplesPerPixel, 7);
    TestEqual(TEXT("Low quality preserves the same physical emitter size"), Exterior->SourceRadius, 24.f);
    Apply(1, false);
    TestTrue(TEXT("Unsupported hardware cannot leave the exterior RT override active"), Exterior->CastRaytracedShadow == ECastRayTracedShadow::Disabled);
    TestTrue(TEXT("Unsupported hardware cannot leave the indoor RT override active"), Indoor->CastRaytracedShadow == ECastRayTracedShadow::Disabled);
    TestEqual(TEXT("Hardware fallback does not resize the exterior emitter"), Exterior->SourceRadius, 24.f);
    Apply(1, true);
    TestTrue(TEXT("Indoor RT recovers after hardware policy availability returns"), Indoor->CastRaytracedShadow == ECastRayTracedShadow::Enabled);
    TestTrue(TEXT("Hardware recovery keeps the exterior on VSM"), Exterior->CastRaytracedShadow == ECastRayTracedShadow::Disabled);
    TestTrue(TEXT("The unselected lamp retains its authored mode"), Other->CastRaytracedShadow == OtherMode);
    TestEqual(TEXT("The unselected lamp retains its sample setting"), Other->SamplesPerPixel, OtherSamples);
    TestEqual(TEXT("An unselected lamp's source size is untouched"), Other->SourceRadius, 50.f);
    TestEqual(TEXT("Radiant output is independent of quality"), Exterior->Intensity, 2500.f);
    TestEqual(TEXT("Softening does not offset the shadow"), Exterior->ShadowBias, .31f);
    TestTrue(TEXT("Softening does not move the lamp"), Exterior->GetComponentLocation().Equals(ExteriorLocation));
    TestTrue(TEXT("Color temperature remains active"), Exterior->bUseTemperature);
    TestEqual(TEXT("Color temperature stays authored"), Exterior->Temperature, 3100.f);
    TestTrue(TEXT("Softening retains the standard scene channel without isolation"), Exterior->LightingChannels.bChannel0
        && !Exterior->LightingChannels.bChannel1 && !Exterior->LightingChannels.bChannel2);
    TestEqual(TEXT("Rect width is preserved"), Indoor->SourceWidth, 120.f);
    TestEqual(TEXT("Rect height is preserved"), Indoor->SourceHeight, 70.f);
    Policy.Reset();
    TestTrue(TEXT("Reset restores the original exterior mode, not the last quality state"), Exterior->CastRaytracedShadow == ECastRayTracedShadow::UseProjectSetting);
    TestEqual(TEXT("Reset restores the original exterior sample count"), Exterior->SamplesPerPixel, 7);
    TestEqual(TEXT("Reset restores the original exterior emitter radius"), Exterior->SourceRadius, 8.f);
    TestTrue(TEXT("Reset restores an independently disabled indoor mode"), Indoor->CastRaytracedShadow == ECastRayTracedShadow::Disabled);
    TestEqual(TEXT("Reset restores the original indoor sample count"), Indoor->SamplesPerPixel, 3);
    TestEqual(TEXT("Reset releases all weak overrides"), Policy.GetManagedLightCount(), 0);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowFrameLightLifecycleTest, "OutOfWindow.Frame.ShadowSelectionLifecycle",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWindowFrameLightLifecycleTest::RunTest(const FString& Parameters)
{
    UWorld* World = UWorld::CreateWorld(EWorldType::Game, false);
    if (!TestNotNull(TEXT("Test world"), World)) return false;
    ON_SCOPE_EXIT { World->DestroyWorld(false); };
    UPointLightComponent* First = MakePoint(World, FVector(500, 0, 0), 1600);
    UPointLightComponent* Second = MakePoint(World, FVector(1000, 0, 0), 1600);
    if (!TestNotNull(TEXT("First source"), First) || !TestNotNull(TEXT("Second source"), Second)) return false;
    First->SetCastRaytracedShadows(ECastRayTracedShadow::Disabled);
    First->SetSamplesPerPixel(5);
    Second->SetCastRaytracedShadows(ECastRayTracedShadow::UseProjectSetting);
    Second->SetSamplesPerPixel(6);
    Second->SetSourceRadius(48);
    TArray<TObjectPtr<ULightComponent>> Lights{First, Second};
    FWindowFrameLighting Policy;
    Policy.Update(TEXT("Alley"), FVector::ZeroVector, TestFrame, Lights, nullptr, 1, true);
    TestEqual(TEXT("The selected small source receives the minimum area"), First->SourceRadius, 24.f);
    TestEqual(TEXT("The farther source retains its larger authored radius"), Second->SourceRadius, 48.f);
    First->GetOwner()->Tags.Add(TEXT("OOWInteriorLight"));
    Policy.Update(TEXT("Alley"), FVector::ZeroVector, TestFrame, Lights, nullptr, 1, true);
    TestTrue(TEXT("A source that becomes ineligible regains its authored shadow mode"), First->CastRaytracedShadow == ECastRayTracedShadow::Disabled);
    TestEqual(TEXT("Deselection restores its original samples"), First->SamplesPerPixel, 5);
    TestEqual(TEXT("Deselection restores the original source radius"), First->SourceRadius, 8.f);
    TestTrue(TEXT("The next qualified lamp stays on VSM"), Second->CastRaytracedShadow == ECastRayTracedShadow::Disabled);
    TestEqual(TEXT("A newly selected larger source is never shrunk"), Second->SourceRadius, 48.f);
    TestEqual(TEXT("Selection never changes exterior SPP"), Second->SamplesPerPixel, 6);
    TestEqual(TEXT("Replacement does not grow the managed-light budget"), Policy.GetManagedLightCount(), 1);
    Policy.Update(TEXT("City"), FVector::ZeroVector, TestFrame, Lights, nullptr, 2, true);
    TestTrue(TEXT("Leaving Alley restores the former selected lamp"), Second->CastRaytracedShadow == ECastRayTracedShadow::UseProjectSetting);
    TestEqual(TEXT("Scene transition preserves authored samples"), Second->SamplesPerPixel, 6);
    Policy.Update(TEXT("Alley"), FVector::ZeroVector, TestFrame, Lights, nullptr, 1, true);
    Policy.Update(TEXT("Alley"), FVector::ZeroVector, FBox(ForceInit), Lights, nullptr, 2, true);
    TestTrue(TEXT("Lost frame geometry restores rather than broadening the override"), Second->CastRaytracedShadow == ECastRayTracedShadow::UseProjectSetting);
    TestEqual(TEXT("Lost geometry releases managed lights"), Policy.GetManagedLightCount(), 0);
    {
        FWindowFrameLighting Scoped;
        Scoped.Update(TEXT("Alley"), FVector::ZeroVector, TestFrame, Lights, nullptr, 2, true);
    }
    TestTrue(TEXT("Owner shutdown restores a still-live scene light"), Second->CastRaytracedShadow == ECastRayTracedShadow::UseProjectSetting);
    TestEqual(TEXT("Owner shutdown restores its authored samples"), Second->SamplesPerPixel, 6);
    return true;
}

#endif
