#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WindowFrame.generated.h"

class UCameraComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class URectLightComponent;
class UStaticMeshComponent;

/** Physical foreground scenery; deliberately independent of Slate/UI visibility. */
UCLASS()
class OUTOFWINDOW_API AWindowFrame : public AActor
{
    GENERATED_BODY()
public:
    AWindowFrame();
    virtual void BeginPlay() override;
    void FitToView(UCameraComponent* Camera, float AspectRatio);
    void SetDaylight(float Daylight);
    void SetRainIntensity(float Intensity);
    float GetRainIntensity() const { return RainIntensity; }
    bool SetStyle(FName Id);
    FName GetStyle() const { return StyleId; }
    bool IsReady() const;
    int32 GetTriangleCount() const { return TriangleCount; }
    FVector2D GetOpeningSize() const { return OpeningSize; }
    int32 GetRoomWallCount() const { return RoomWalls.Num(); }
    float GetRoomLampLumens() const;

private:
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Frame;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> RainGlass;
    UPROPERTY() TObjectPtr<URectLightComponent> RoomBounce;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> RoomWalls;
    UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> RoomMaterial;
    UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> Materials;
    UPROPERTY() TSoftObjectPtr<UMaterialInterface> MaterialSource;
    UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> RainMaterial;
    UPROPERTY() TSoftObjectPtr<UMaterialInterface> RainMaterialSource;
    FName StyleId = TEXT("graphite");
    float RainIntensity = 0;
    FVector2D OpeningSize = FVector2D::ZeroVector;
    float LastFov = 0, LastAspect = 0;
    int32 TriangleCount = 0;
};
