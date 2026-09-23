#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WindowPrecipitation.generated.h"

class UInstancedStaticMeshComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UStaticMesh;

/** Fixed-view world-space rain/snow. Particle motion runs in the vertex shader. */
UCLASS()
class OUTOFWINDOW_API AWindowPrecipitation : public AActor
{
    GENERATED_BODY()

public:
    AWindowPrecipitation();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;

    /** Rebuild only when selecting a scene/view, never for each animation frame. */
    void SetView(const FVector& CameraLocation, const FVector& CameraForward);
    /** Amounts are 0..1; wind is a world-space velocity in centimetres/second. */
    void SetWeather(float RainAmount, float SnowAmount, const FVector& WindVelocity);

private:
    void CreateParticles(UInstancedStaticMeshComponent* Component, int32 Count, bool bSnow,
                         const FVector& CameraForward);
    void CreateSplashes(const FVector& CameraLocation, const FVector& CameraForward);

    UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> Rain;
    UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> Snow;
    UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> Splashes;
    UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> RainMaterial;
    UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> SnowMaterial;
    UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> SplashMaterial;
    UPROPERTY() TSoftObjectPtr<UMaterialInterface> RainSource;
    UPROPERTY() TSoftObjectPtr<UMaterialInterface> SnowSource;
    UPROPERTY() TSoftObjectPtr<UMaterialInterface> SplashSource;
    UPROPERTY() TSoftObjectPtr<UStaticMesh> PlaneSource;

    FVector VolumeMin = FVector::ZeroVector;
    FVector VolumeSize = FVector(6000.0, 6000.0, 5600.0);
    FVector Wind = FVector::ZeroVector;
    FVector TargetWind = FVector::ZeroVector;
    FVector WindOffset = FVector::ZeroVector;
    float RainAmount = 0.0f;
    float SnowAmount = 0.0f;
    float TargetRain = 0.0f;
    float TargetSnow = 0.0f;
};
