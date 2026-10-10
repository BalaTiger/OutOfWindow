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
    Birds->SetConditions(1, 1.f, FVector(160, 90, 0));
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
    // Each crossing samples its own depth, lateral offset, heading and pitch, so
    // consecutive flights enter the sky from different places.
    TSet<FIntVector> Entries;
    TSet<FIntVector> Separations;
    // Enough flights that several carry more than one bird; the size is random
    // per crossing, so a short window can land on singleton flights only.
    for (int32 Flight = 0; Flight < 8; ++Flight)
    {
        int32 Guard = 0;
        while (Birds->GetActiveCount() == 0 && ++Guard < 3000) Birds->Tick(.1f);
        if (Birds->GetActiveCount() == 0) break;
        const FVector Entry = Birds->GetFirstBirdLocation();
        Entries.Add(FIntVector(FMath::RoundToInt(Entry.X), FMath::RoundToInt(Entry.Y), FMath::RoundToInt(Entry.Z)));
        bool bSeparated = false;
        Guard = 0;
        while (Birds->GetActiveCount() != 0 && ++Guard < 3000)
        {
            Birds->Tick(.1f);
            // Once the follower is up, its spacing from the leader is this
            // flight's relative geometry; it should differ flight to flight.
            if (!bSeparated && Birds->GetActiveCount() > 1)
            {
                const FVector Gap = Birds->GetBirdLocation(1) - Birds->GetBirdLocation(0);
                Separations.Add(FIntVector(FMath::RoundToInt(Gap.X), FMath::RoundToInt(Gap.Y), FMath::RoundToInt(Gap.Z)));
                bSeparated = true;
            }
        }
    }
    TestTrue(TEXT("Consecutive flights follow different paths"), Entries.Num() > 1);
    TestTrue(TEXT("Flock spacing differs between flights"), Separations.Num() > 1);
    TArray<UStaticMeshComponent*> Components;
    Birds->GetComponents(Components);
    TestEqual(TEXT("Component count stays bounded across flights"), Components.Num(), 9);
    for (UStaticMeshComponent* Component : Components)
        TestEqual(TEXT("Birds never collide with the scene"), Component->GetCollisionEnabled(), ECollisionEnabled::NoCollision);
    Birds->SetConditions(0, 1.f, FVector::ZeroVector);
    Advance(60);
    TestEqual(TEXT("Night suppresses birds"), Birds->GetActiveCount(), 0);
    const int32 Completed = Birds->GetCompletedFlights();
    // Rain and snow are rare but not silent: a flight already scheduled when the
    // weather turned still crosses, then the slowed cadence takes over.
    Birds->SetConditions(1, .05f, FVector::ZeroVector);
    Advance(60);
    TestEqual(TEXT("Rain and snow keep flights rare"), Birds->GetActiveCount(), 0);
    const int32 BeforeWind = Birds->GetCompletedFlights();
    Birds->SetConditions(1, 1.f, FVector(1500, 0, 0));
    Advance(60);
    TestEqual(TEXT("Strong wind suppresses all new flights"), Birds->GetCompletedFlights(), BeforeWind);
    Birds->SetConditions(1, 1.f, FVector::ZeroVector);
    Advance(60);
    TestTrue(TEXT("Fair daylight resumes the schedule"), Birds->GetCompletedFlights() > BeforeWind);
    // Same 120 s window, same wind: clear weather flies, sparse weather does not.
    const int32 Fair = Birds->GetCompletedFlights();
    Advance(120);
    const int32 FairDelta = Birds->GetCompletedFlights() - Fair;
    Birds->SetConditions(1, .05f, FVector::ZeroVector);
    Advance(240);
    const int32 SparseDelta = Birds->GetCompletedFlights() - Fair - FairDelta;
    TestTrue(TEXT("Clear weather flies more often than rain or snow"), FairDelta > SparseDelta);
    // The sparse schedule is slow, not a hard stop: within a long enough window
    // rain still lets a flock through.
    const int32 BeforeLongWait = Birds->GetCompletedFlights();
    Advance(1200);
    TestTrue(TEXT("Rain and snow still fly eventually"), Birds->GetCompletedFlights() > BeforeLongWait);
    World->DestroyWorld(false);
    return true;
}

#endif
