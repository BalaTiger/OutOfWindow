#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WindowDesktop.h"
#include "WindowFrameLighting.h"
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
class UStaticMesh;

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
    bool IsStartupSceneReady() const { return bStartupSceneInitialized && bCameraBound; }
    FString GetStartupSceneError() const { return bStartupSceneInitialized ? FString::Join(MissingTags, TEXT(", ")) : FString(); }
    TFunction<void(FName)> DesktopAction;
    TFunction<void()> RestoreInterface;

private:
    friend class FWindowLocationTest;
    void FindSceneActors();
    void BindCamera();
    void MakeInterface();
    void ApplyLighting(float DeltaSeconds);
    void UpdateCloudSampling(float DeltaSeconds);
    void UpdateApprovedClouds(float DeltaSeconds, const FString& DisplayedWeather);
    void UpdateMaterials(float DeltaSeconds);
    void UpdateFrameShadowLighting();
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
    UPROPERTY() TObjectPtr<UDirectionalLightComponent> Moon;
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
    TUniquePtr<FWindowFrameLighting> FrameLighting;
    TWeakObjectPtr<UStaticMesh> FrameLightingMesh;
    bool bFrameLightingDirty = true;
    bool bFrameLightingEnabled = false;
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
    float MoonElevation = 0, MoonIlluminatedFraction = 0;
    float Daylight = 1;
    float Wetness = 0;
    float Water = 0;
    float MaterialTimer = 0;
    float LastSkyCapture = -100;
    float LastWindowReflectionCapture = -100;
    int32 WindowReflectionCaptureRequests = 0;
    float FastLightingUntil = 0;
    float SolarMinutes = 0;
    // Only active in an explicitly fixed-step HDR/Houdini diagnostic process.
    bool PaceDiagnosticTick(float DeltaSeconds);
    double DiagnosticWallFPS = 0.0;
    double DiagnosticLastWallStart = -1.0;
    int32 DiagnosticTickCount = 0;
    float TestSeconds = 12;
    float TestStartedAt = 0;
    float VerticalFov = 0;
    float BaseFogDensity = .008f;
    float BaseRayleighScattering = 0, BaseMieScattering = 0, BaseMieAbsorption = 0;
    bool bApprovedCloudRoute = false, bApprovedMixInitialized = false;
    float ApprovedLowWeight = 0, ApprovedCiWeight = 0, ApprovedRainWeight = 0;
    float ApprovedBoundsBottom = 1.2f, ApprovedBoundsTop = 8.38f;
    int32 ApprovedOriginalMinSamples = 2;
    float ApprovedOriginalSampleDistance = 5.f;
    FLinearColor ApprovedOriginKm = FLinearColor(0, 0, 1, 0);
    float Cloudiness = .25f;
    float Storminess = 0;
    float VisibleSkyFraction = -1, VisibleSkyPixels = -1;
    float CloudSampleScale = 1, CloudTargetSampleScale = 1;
    FVector2D CloudDriftUV = FVector2D::ZeroVector;
    FVector2D CloudWindMetersPerSecond = FVector2D::ZeroVector;
    float SunAzimuth = 0;
    double SceneNorthYaw = 0;
    FVector2D LastViewportSize = FVector2D::ZeroVector;
    FString CapturePath;
    FString CapturingFramePath;
    TArray<FString> TransmittancePreviousFiles;
    TArray<FString> TestWeatherSequence;
    FDelegateHandle ScreenshotHandle;
    int32 ExitFrames = -1;
    int32 CaptureFrames = 1;
    int32 CapturedFrames = 0;
    float CaptureInterval = .125f;
    bool bTestMode = false;
    bool bLegacyLighting = false;
    bool bLegacyClouds = false;
    bool bEmptyCloudReference = false;
    bool bSunSweep = false;
    bool bCaptureRequested = false;
    bool bCameraBound = false;
    bool bStartupSceneInitialized = false;
    bool bFetching = false;
    bool bChangingLevel = false;
    bool bCollapsed = false;
    bool bPrivacyDismissed = false;
};
