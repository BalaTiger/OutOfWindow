#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WindowDesktop.h"
#include "WindowTraffic.h"
#include "WindowDirector.generated.h"

class ACameraActor;
class APostProcessVolume;
class UDirectionalLightComponent;
class ULightComponent;
class USkyLightComponent;
class USceneCaptureComponentCube;
class UTextureRenderTargetCube;
class USkyAtmosphereComponent;
class UExponentialHeightFogComponent;
class UVolumetricCloudComponent;
class UMaterialInstanceDynamic;
class AWindowPrecipitation;
class UAudioComponent;
class USoundWaveProcedural;
class AWindowBirds;
class AWindowFrame;
class SWindowVisibilityButton;
class SWidget;
class IHttpRequest;
class IConsoleObject;
class FWindowSkySampling;

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
    UFUNCTION(Exec) void OOWFrame(const FString& Style);
    UFUNCTION(Exec) void OOWAudit();

    void RefreshWeather();
    TFunction<void(FName)> DesktopAction;
    TFunction<void()> RestoreInterface;

private:
    friend class FWindowLocationTest;
    void FindSceneActors();
    void BindCamera();
    void MakeInterface();
    void ApplyLighting(float DeltaSeconds);
    void UpdateCloudSampling(float DeltaSeconds);
    void UpdateMaterials(float DeltaSeconds);
    void UpdateAudio();
    void ToggleAudio();
    void FetchForecast(double Latitude, double Longitude, const FString& City, const FString& Timezone);
    void UseOfflineWeather();
    void ApplyLocation(bool bFollowIP, double Latitude, double Longitude, const FString& City, double UtcOffset);
    void RegisterCommands();
    void DesktopButton(FName Action);
    FString ActualWeather() const;
    FText StatusText() const;
    FText ClockText() const;

    UPROPERTY() TObjectPtr<ACameraActor> Camera;
    UPROPERTY() TObjectPtr<UDirectionalLightComponent> Sun;
    UPROPERTY() TArray<TObjectPtr<ULightComponent>> NightLights;
    UPROPERTY() TObjectPtr<USkyLightComponent> Sky;
    UPROPERTY() TObjectPtr<USceneCaptureComponentCube> WindowReflectionCapture;
    UPROPERTY() TObjectPtr<UTextureRenderTargetCube> WindowReflectionTexture;
    UPROPERTY() TObjectPtr<USkyAtmosphereComponent> Atmosphere;
    UPROPERTY() TObjectPtr<UExponentialHeightFogComponent> Fog;
    UPROPERTY() TObjectPtr<UVolumetricCloudComponent> Cloud;
    UPROPERTY() TObjectPtr<APostProcessVolume> PostProcess;
    UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> Materials;
    UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> CloudMaterial;
    UPROPERTY() TObjectPtr<AWindowPrecipitation> Precipitation;
    UPROPERTY() TObjectPtr<AWindowBirds> Birds;
    UPROPERTY() TObjectPtr<AWindowFrame> WindowFrame;
    UPROPERTY() TObjectPtr<UAudioComponent> AmbientAudio;
    UPROPERTY() TObjectPtr<USoundWaveProcedural> NoiseWave;

    TSharedPtr<SWidget> Interface;
    TSharedPtr<SWindowVisibilityButton> VisibilityControl;
    TSharedPtr<FWindowSkySampling, ESPMode::ThreadSafe> SkySampling;
    TSharedPtr<IHttpRequest, ESPMode::ThreadSafe> GeoRequest;
    TSharedPtr<IHttpRequest, ESPMode::ThreadSafe> ForecastRequest;
    TUniquePtr<FWindowDesktop> Desktop;
    TArray<IConsoleObject*> Commands;
    TArray<float> FrameTimes;
    TArray<float> NightLightIntensities;
    TArray<FString> MissingTags;
    struct FCarPart { TWeakObjectPtr<AActor> Actor; FVector Origin; FRotator Rotation; int32 Car; };
    TArray<FCarPart> CarParts;
    TMap<int32, FVector> CarOrigins;
    FWindowTraffic Traffic;
    FRandomStream Random;
    float SolarElevation = 0;
    float Daylight = 1;
    float Wetness = 0;
    float Water = 0;
    float MaterialTimer = 0;
    float LastSkyCapture = -100;
    float LastWindowReflectionCapture = -100;
    int32 WindowReflectionCaptureRequests = 0;
    float FastLightingUntil = 0;
    float SolarMinutes = 0;
    float TestSeconds = 12;
    float TestStartedAt = 0;
    float VerticalFov = 0;
    float BaseFogDensity = .008f;
    float BaseRayleighScattering = 0, BaseMieScattering = 0, BaseMieAbsorption = 0;
    float Cloudiness = .25f;
    float Storminess = 0;
    float VisibleSkyFraction = -1, VisibleSkyPixels = -1;
    float CloudSampleScale = 1, CloudTargetSampleScale = 1;
    FVector2D CloudDriftUV = FVector2D::ZeroVector;
    FVector2D CloudWindMetersPerSecond = FVector2D::ZeroVector;
    float SunAzimuth = 0;
    FVector2D LastViewportSize = FVector2D::ZeroVector;
    FString CapturePath;
    FDelegateHandle ScreenshotHandle;
    int32 ExitFrames = -1;
    int32 CaptureFrames = 1;
    int32 CapturedFrames = 0;
    float CaptureInterval = .125f;
    bool bTestMode = false;
    bool bSunSweep = false;
    bool bCaptureRequested = false;
    bool bCameraBound = false;
    bool bFetching = false;
    bool bChangingLevel = false;
    bool bCollapsed = false;
    bool bPrivacyDismissed = false;
};
