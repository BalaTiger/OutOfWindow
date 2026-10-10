#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WindowBirds.generated.h"

class UMaterialInterface;
class UMaterialInstanceDynamic;
class UStaticMesh;
class UStaticMeshComponent;

/** A few distant, reusable birds crossing the alley's upper sky opening. */
UCLASS()
class OUTOFWINDOW_API AWindowBirds : public AActor
{
    GENERATED_BODY()

public:
    AWindowBirds();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;

    void SetView(const FVector& CameraLocation, const FVector& CameraForward);
    // WeatherActivity scales the schedule: 1 = fair weather, 0 = none. Rain and
    // snow stay flyable, just rare.
    void SetConditions(float Daylight, float WeatherActivity, const FVector& WindVelocity);
    int32 GetActiveCount() const;
    int32 GetCompletedFlights() const { return CompletedFlights; }
    float GetFlightAge() const { return FlightAge; }
    FVector GetFirstBirdLocation() const;
    FVector GetBirdLocation(int32 Index) const;
    bool IsReady() const { return BodyMesh != nullptr && WingMesh != nullptr && Material != nullptr; }

private:
    void HideBirds();
    void StartFlight();

    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Bodies;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Wings;
    UPROPERTY() TObjectPtr<UStaticMesh> BodyMesh;
    UPROPERTY() TObjectPtr<UStaticMesh> WingMesh;
    UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> Material;
    UPROPERTY() TSoftObjectPtr<UMaterialInterface> MaterialSource;

    FRandomStream Random = FRandomStream(23891);
    FVector ViewLocation = FVector::ZeroVector;
    FVector ViewForward = FVector::ForwardVector;
    FVector ViewRight = FVector::RightVector;
    FVector Wind = FVector::ZeroVector;
    // Paths are sampled in this plane, so a crossing can tilt off horizontal.
    FVector PathLateral = FVector::RightVector;
    FVector FlightStart = FVector::ZeroVector;
    FVector FlightEnd = FVector::ZeroVector;
    float CrossSign = 1.0f; // Which way this crossing runs across the sky.
    // Per-bird variation, resampled every crossing: where it sits in the group,
    // how fast it flies, how late it enters, whether it climbs or dives, and its
    // own flap phase and cadence. So the flock is a loose group, not a rigid
    // ladder of evenly spaced copies.
    struct FBirdVariation
    {
        FVector2D Offset = FVector2D::ZeroVector;
        float Speed = 1.0f;  // Its own pace along the crossing.
        float Lag = 0.0f;    // Seconds it trails the leader on entry.
        float Climb = 0.0f;  // Height gained over the crossing, so paths diverge.
        float Phase = 0.0f;  // Flap phase offset.
        float Rate = 4.6f;   // Flap frequency.
    };
    FBirdVariation Flock[3];
    // Longest bird's stay in the sky this crossing, for the finish test.
    float FlightLifetime = 9.0f;
    float WaitRemaining = 7.5f;
    float FlightAge = -1.0f;
    float FlightDuration = 8.0f;
    int32 FlockSize = 3;
    int32 CompletedFlights = 0;
    bool bHasView = false;
    bool bPermitted = false;
    float Activity = 0.f;
};
