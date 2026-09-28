#if WITH_DEV_AUTOMATION_TESTS

#include "../WindowBirds.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowBirdsTest, "OutOfWindow.Alley.BirdsLifecycle",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWindowBirdsTest::RunTest(const FString& Parameters)
{
    UWorld* World = UWorld::CreateWorld(EWorldType::Game, false);
    if (!TestNotNull(TEXT("Test world"), World)) return false;
    AWindowBirds* Birds = World->SpawnActor<AWindowBirds>();
    if (!TestNotNull(TEXT("Bird actor"), Birds)) { World->DestroyWorld(false); return false; }
    Birds->DispatchBeginPlay();
    TestTrue(TEXT("Original bird meshes build without imported assets"), Birds->IsReady());
    Birds->SetView(FVector(-2000, -20800, 2300), FVector(-.5647, -.8253, 0));
    Birds->SetConditions(1, true, FVector(160, 90, 0));
    auto Advance = [Birds](float Seconds)
    {
        for (int32 Frame = 0; Frame < FMath::RoundToInt(Seconds * 10); ++Frame) Birds->Tick(.1f);
    };
    Advance(6);
    TestEqual(TEXT("Birds are occasional, with a quiet initial delay"), Birds->GetActiveCount(), 0);
    Advance(6);
    TestEqual(TEXT("First pass is visible around twelve seconds"), Birds->GetActiveCount(), 3);
    Advance(7);
    TestEqual(TEXT("Birds disappear after crossing"), Birds->GetActiveCount(), 0);
    TestEqual(TEXT("First pass completes"), Birds->GetCompletedFlights(), 1);
    Advance(60);
    TestTrue(TEXT("A later pass reuses the birds"), Birds->GetCompletedFlights() >= 2);
    TArray<UStaticMeshComponent*> Components;
    Birds->GetComponents(Components);
    TestEqual(TEXT("Component count stays bounded across flights"), Components.Num(), 9);
    for (UStaticMeshComponent* Component : Components)
        TestEqual(TEXT("Birds never collide with the scene"), Component->GetCollisionEnabled(), ECollisionEnabled::NoCollision);
    Birds->SetConditions(0, true, FVector::ZeroVector);
    Advance(60);
    TestEqual(TEXT("Night suppresses birds"), Birds->GetActiveCount(), 0);
    const int32 Completed = Birds->GetCompletedFlights();
    Birds->SetConditions(1, false, FVector::ZeroVector);
    Advance(60);
    TestEqual(TEXT("Rain, snow and fog suppress all new flights"), Birds->GetCompletedFlights(), Completed);
    Birds->SetConditions(1, true, FVector(1500, 0, 0));
    Advance(60);
    TestEqual(TEXT("Strong wind suppresses all new flights"), Birds->GetCompletedFlights(), Completed);
    Birds->SetConditions(1, true, FVector::ZeroVector);
    Advance(60);
    TestTrue(TEXT("Fair daylight resumes the schedule"), Birds->GetCompletedFlights() > Completed);
    World->DestroyWorld(false);
    return true;
}

#endif
