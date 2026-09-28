#pragma once

#include "CoreMinimal.h"
#include "UObject/WeakObjectPtr.h"

class AActor;
class USpotLightComponent;

// City boulevard only. Metres and seconds internally; actor transforms use UE centimetres.
struct FWindowTrafficCar
{
    int32 Id = 0, Direction = -1, Lane = 0, TargetLane = 0;
    float Position = 0, Speed = 0, DesiredSpeed = 0;
    float ChangeTime = 0, Cooldown = 0;
    float GroundZ = 0;
    bool IsChangingLane() const { return Lane != TargetLane; }
    bool Occupies(int32 TestLane) const { return Lane == TestLane || TargetLane == TestLane; }
};

struct FWindowTrafficHeadlight
{
    int32 CarId = INDEX_NONE;
    FVector Location = FVector::ZeroVector;
    FRotator Rotation = FRotator::ZeroRotator;
    float Strength = 0;
};

struct FWindowTraffic
{
    static constexpr int32 MaxHeadlights = 8;
    // Recycle just before the distant junction, keeping cars off its pedestrian plaza.
    static constexpr float NearY = 1600.f, FarY = -39000.f;
    static constexpr float RoadLength = (NearY - FarY) / 100.f;
    // Envelope includes the 4.3 m sedan's corners while yawed during a lane change.
    static constexpr float CarLength = 4.9f, MinimumGap = 2.5f, ChangeDuration = 3.2f;
    TArray<FWindowTrafficCar> Cars;
    int32 CompletedChanges = 0, OvertakeChanges = 0, Wraps = 0;
    float MinimumObservedGap = RoadLength;
    int32 ActiveHeadlights = 0;

    void Add(int32 Id, const FVector& Origin);
    void Tick(float DeltaSeconds, const FString& Weather);
    FVector Location(const FWindowTrafficCar& Car, float Z) const;
    float Yaw(const FWindowTrafficCar& Car) const;
    float Gap(const FWindowTrafficCar& Car, const FWindowTrafficCar& Other) const;
    TArray<FWindowTrafficHeadlight> HeadlightTargets(const FVector& CameraLocation, float Night) const;
    // Owner retains at most eight transient, shadowless road-light components.
    // Call after the car transforms update; Night is 1 - scene daylight.
    void UpdateHeadlights(AActor* Owner, const FVector& CameraLocation, float Night, float DeltaSeconds);

private:
    struct FHeadlamp
    {
        TWeakObjectPtr<USpotLightComponent> Light;
        int32 CarId = INDEX_NONE;
        float Strength = 0;
    };
    TArray<FHeadlamp> Headlamps;
    double Accumulator = 0;
    void Step(float Dt, float SpeedScale, float Headway);
    const FWindowTrafficCar* Leader(const FWindowTrafficCar& Car, int32 Lane) const;
    bool CanChange(const FWindowTrafficCar& Car, int32 Lane, float Headway) const;
};
