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
    void SetConditions(float Daylight, bool bFairWeather, const FVector& WindVelocity);
    int32 GetActiveCount() const;
    int32 GetCompletedFlights() const { return CompletedFlights; }
    float GetFlightAge() const { return FlightAge; }
    FVector GetFirstBirdLocation() const;
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
    FVector FlightStart = FVector::ZeroVector;
    FVector FlightEnd = FVector::ZeroVector;
    float WaitRemaining = 7.5f;
    float FlightAge = -1.0f;
    float FlightDuration = 8.0f;
    int32 FlockSize = 3;
    int32 CompletedFlights = 0;
    bool bHasView = false;
    bool bPermitted = false;
};
