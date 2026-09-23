#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WindowDesktop.h"
#include "WindowDirector.generated.h"

class ACameraActor;
class APostProcessVolume;
class UDirectionalLightComponent;
class UPointLightComponent;
class USkyLightComponent;
class UExponentialHeightFogComponent;
class UVolumetricCloudComponent;
class UMaterialInstanceDynamic;
class AWindowPrecipitation;
class UAudioComponent;
class USoundWaveProcedural;
class SWidget;
class IHttpRequest;
class IConsoleObject;

UCLASS()
class OUTOFWINDOW_API AWindowDirector : public AActor
{
    GENERATED_BODY()

public:
    AWindowDirector();
    virtual ~AWindowDirector() override;
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

    UFUNCTION(Exec) void OOWTime(float Hour);
    UFUNCTION(Exec) void OOWWeather(const FString& Mode);
    UFUNCTION(Exec) void OOWScene(const FString& Scene);
    UFUNCTION(Exec) void OOWQuality(int32 Quality);
    UFUNCTION(Exec) void OOWAudit();

    void RefreshWeather();
    void SetCompactMode(bool bEnabled);
    TFunction<void(FName)> DesktopAction;

private:
    void FindSceneActors();
    void BindCamera();
    void MakeInterface();
    void ApplyLighting(float DeltaSeconds);
    void UpdateMaterials(float DeltaSeconds);
    void UpdateAudio();
    void ToggleAudio();
    void FetchForecast(double Latitude, double Longitude, const FString& City, const FString& Timezone);
    void UseOfflineWeather();
    void RegisterCommands();
    void DesktopButton(FName Action);
    FString ActualWeather() const;
    FText StatusText() const;
    FText ClockText() const;

    UPROPERTY() TObjectPtr<ACameraActor> Camera;
    UPROPERTY() TObjectPtr<UDirectionalLightComponent> Sun;
    UPROPERTY() TArray<TObjectPtr<UPointLightComponent>> NightLights;
    UPROPERTY() TObjectPtr<USkyLightComponent> Sky;
    UPROPERTY() TObjectPtr<UExponentialHeightFogComponent> Fog;
    UPROPERTY() TObjectPtr<UVolumetricCloudComponent> Cloud;
    UPROPERTY() TObjectPtr<APostProcessVolume> PostProcess;
    UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> Materials;
    UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> CloudMaterial;
    UPROPERTY() TObjectPtr<AWindowPrecipitation> Precipitation;
    UPROPERTY() TObjectPtr<UAudioComponent> AmbientAudio;
    UPROPERTY() TObjectPtr<USoundWaveProcedural> NoiseWave;

    TSharedPtr<SWidget> Interface;
    TSharedPtr<IHttpRequest, ESPMode::ThreadSafe> GeoRequest;
    TSharedPtr<IHttpRequest, ESPMode::ThreadSafe> ForecastRequest;
    TUniquePtr<FWindowDesktop> Desktop;
    TArray<IConsoleObject*> Commands;
    TArray<float> FrameTimes;
    TArray<float> NightLightIntensities;
    TArray<FString> MissingTags;
    struct FCarPart { TWeakObjectPtr<AActor> Actor; FVector Origin; int32 Car; };
    TArray<FCarPart> CarParts;
    TMap<int32, float> CarStartY;
    FRandomStream Random;
    float SolarElevation = 0;
    float Daylight = 1;
    float Wetness = 0;
    float Water = 0;
    float MaterialTimer = 0;
    float LastSkyCapture = -100;
    float FastLightingUntil = 0;
    float SolarMinutes = 0;
    float TestSeconds = 12;
    float TestStartedAt = 0;
    float VerticalFov = 0;
    float BaseFogDensity = .008f;
    float SunAzimuth = 0;
    FVector2D LastViewportSize = FVector2D::ZeroVector;
    FString CapturePath;
    FDelegateHandle ScreenshotHandle;
    int32 ExitFrames = -1;
    bool bTestMode = false;
    bool bSunSweep = false;
    bool bCaptureRequested = false;
    bool bCameraBound = false;
    bool bFetching = false;
    bool bChangingLevel = false;
    bool bCompact = false;
    bool bCollapsed = false;
    bool bPrivacyDismissed = false;
};
