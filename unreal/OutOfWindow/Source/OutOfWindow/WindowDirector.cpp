#include "WindowDirector.h"
#include "WindowVisibilityButton.h"
#include "WindowDesktop.h"
#include "WindowPrecipitation.h"
#include "WindowBirds.h"
#include "WindowFrame.h"
#include "WindowWeather.h"
#include "WindowSkySampling.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/AudioComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/LightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/MeshComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/SceneCaptureComponentCube.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/VolumetricCloudComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "SceneView.h"
#include "RHI.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/StaticMesh.h"
#include "Engine/TextureRenderTargetCube.h"
#include "EngineUtils.h"
#include "GameFramework/GameUserSettings.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HttpModule.h"
#include "ImageUtils.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/CommandLine.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/App.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Sound/SoundWaveProcedural.h"
#include "Styling/CoreStyle.h"
#include "TimerManager.h"
#include "UnrealClient.h"
#if WITH_EDITOR
#include "ShaderCompiler.h"
#endif
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SComboButton.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SNumericEntryBox.h"
#include "Widgets/Input/SSlider.h"
#include "Widgets/Colors/SComplexGradient.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Layout/SBackgroundBlur.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Brushes/SlateDynamicImageBrush.h"
#include "Brushes/SlateNoResource.h"
#include "Brushes/SlateRoundedBoxBrush.h"
#include "Framework/Application/SlateApplication.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include <limits>
#endif

namespace
{
struct FWindowSession
{
    FString Scene = TEXT("Alley"), Weather = TEXT("real"), City = TEXT("上海"), Timezone = TEXT("Asia/Shanghai");
    FString FrameStyle = TEXT("graphite");
    double Latitude = 31.23, Longitude = 121.47, OffsetSeconds = 28800;
    double Temperature = 22, CloudCover = 35, Precipitation = 0, WindSpeed = 8, WindDirection = 240, Gust = 8;
    int32 WeatherCode = 1, Quality = 1;
    float Hour = 10, Wetness = 0, Water = 0;
    bool bLiveTime = true, bAudio = false, bHasWeather = false, bFallback = true, bTest = false;
    bool bRefreshPending = false;
    bool bFrameStyleInitialized = false;
    bool bLocationInitialized = false, bFollowIP = false;
    FString ManualCity = TEXT("上海");
    double ManualLatitude = 31.23, ManualLongitude = 121.47, ManualUtcOffset = 8;
    bool bCollapsed = false, bPrivacyDismissed = false;
};
FWindowSession Session;
bool ValidLocation(double Latitude, double Longitude, double UtcOffset)
{
    return FMath::IsFinite(Latitude) && FMath::Abs(Latitude) <= 90
        && FMath::IsFinite(Longitude) && FMath::Abs(Longitude) <= 180
        && FMath::IsFinite(UtcOffset) && UtcOffset >= -12 && UtcOffset <= 14;
}
TAutoConsoleVariable<float> NightBloom(TEXT("oow.NightBloom"), 1.3f, TEXT("Bloom intensity for OOWWindowLookdev volumes."));
TAutoConsoleVariable<float> NightBloomSize(TEXT("oow.NightBloomSize"), 5.5f, TEXT("Bloom size scale for OOWWindowLookdev volumes."));
TAutoConsoleVariable<float> NightExposureBias(TEXT("oow.NightExposureBias"), -1.15f, TEXT("Night exposure bias for OOWWindowLookdev volumes."));
TAutoConsoleVariable<float> CloudSampleBudget(TEXT("oow.CloudSampleBudget"), 200000.f, TEXT("Reference internal sky pixels at cloud sample scale 1; bounded by the selected quality preset."));

double Number(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key, double Fallback)
{
    double Value = Fallback;
    if (Object) Object->TryGetNumberField(Key, Value);
    return FMath::IsFinite(Value) ? Value : Fallback;
}

bool ReadJson(const FHttpResponsePtr& Response, bool bSuccess, TSharedPtr<FJsonObject>& Json)
{
    return bSuccess && Response.IsValid() && EHttpResponseCodes::IsOk(Response->GetResponseCode())
        && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Response->GetContentAsString()), Json) && Json.IsValid();
}

FDateTime LocalNow() { return Session.bTest ? FDateTime(2026, 9, 23) + FTimespan::FromHours(Session.Hour) : FDateTime::UtcNow() + FTimespan::FromSeconds(Session.OffsetSeconds); }
float Smooth(float A, float B, float Value) { const float T = FMath::Clamp((Value - A) / (B - A), 0.f, 1.f); return T * T * (3.f - 2.f * T); }

int32 ActiveWeatherCode() { return Session.Weather == TEXT("real") ? Session.WeatherCode : WindowWeather::CodeForPreview(Session.Weather); }

bool ShouldCaptureWindowReflection(float Elapsed, float LastCapture, float FastUntil)
{
    // Let the weather interpolation settle before returning to the slow cadence.
    const float Interval = Elapsed < 10.f || Elapsed < FastUntil + 6.f ? 2.f : 30.f;
    return Elapsed > 2.f && Elapsed - LastCapture >= Interval;
}

void SetCVar(const TCHAR* Name, int32 Value)
{
    if (IConsoleVariable* Variable = IConsoleManager::Get().FindConsoleVariable(Name)) Variable->Set(Value, ECVF_SetByCode);
}
}

AWindowDirector::AWindowDirector()
{
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    AmbientAudio = CreateDefaultSubobject<UAudioComponent>(TEXT("AmbientSound"));
    AmbientAudio->SetupAttachment(RootComponent);
    AmbientAudio->bAutoActivate = false;
    AmbientAudio->bAllowSpatialization = false;
    AmbientAudio->bIsUISound = true;
    Random.Initialize(92119);
}

AWindowDirector::~AWindowDirector() = default;

void AWindowDirector::BeginPlay()
{
    Super::BeginPlay();
    bTestMode = FParse::Value(FCommandLine::Get(), TEXT("OOWCapture="), CapturePath);
    Session.bTest = bTestMode;
    if (!bTestMode && !Session.bLocationInitialized)
    {
        const TCHAR* Section = TEXT("OutOfWindow.Location");
        GConfig->GetBool(Section, TEXT("FollowIP"), Session.bFollowIP, GGameUserSettingsIni);
        GConfig->GetString(Section, TEXT("City"), Session.ManualCity, GGameUserSettingsIni);
        double Latitude = 31.23, Longitude = 121.47, Offset = 8;
        GConfig->GetDouble(Section, TEXT("Latitude"), Latitude, GGameUserSettingsIni);
        GConfig->GetDouble(Section, TEXT("Longitude"), Longitude, GGameUserSettingsIni);
        GConfig->GetDouble(Section, TEXT("UtcOffset"), Offset, GGameUserSettingsIni);
        if (ValidLocation(Latitude, Longitude, Offset))
        {
            Session.ManualLatitude = Latitude; Session.ManualLongitude = Longitude; Session.ManualUtcOffset = Offset;
        }
        Session.bLocationInitialized = true;
    }
    if (bTestMode)
    {
        UseOfflineWeather();
        Session.bLiveTime = false;
        Session.bAudio = false;
        Session.Wetness = Session.Water = 0;
        FParse::Value(FCommandLine::Get(), TEXT("OOWTestSeconds="), TestSeconds);
        TestSeconds = FMath::Clamp(TestSeconds, 1.f, 300.f);
        FParse::Value(FCommandLine::Get(), TEXT("OOWCaptureFrames="), CaptureFrames);
        FParse::Value(FCommandLine::Get(), TEXT("OOWCaptureInterval="), CaptureInterval);
        CaptureFrames = FMath::Clamp(CaptureFrames, 1, 240);
        CaptureInterval = FMath::Clamp(CaptureInterval, .05f, 2.f);
    }
    Session.Scene = UGameplayStatics::GetCurrentLevelName(this, true);
    bCollapsed = Session.bCollapsed;
    bPrivacyDismissed = Session.bPrivacyDismissed;
    Wetness = Session.Wetness;
    Water = Session.Water;
    FindSceneActors();
    BindCamera();
    if (Camera && !(bTestMode && FParse::Param(FCommandLine::Get(), TEXT("OOWTestNoFrame"))))
    {
        WindowFrame = GetWorld()->SpawnActor<AWindowFrame>();
        OOWFrame(Session.FrameStyle);
        if (!Session.bFrameStyleInitialized)
        {
            FString StartFrame;
            if (FParse::Value(FCommandLine::Get(), TEXT("OOWFrame="), StartFrame)) OOWFrame(StartFrame);
            Session.bFrameStyleInitialized = true;
        }
    }
    if (Session.Scene == TEXT("Alley") && Camera && !WindowReflectionCapture)
    {
        WindowReflectionTexture = NewObject<UTextureRenderTargetCube>(this);
        WindowReflectionTexture->ClearColor = FLinearColor::Black;
        WindowReflectionTexture->bForceLinearGamma = true;
        WindowReflectionTexture->bAutoGenerateMips = true;
        WindowReflectionTexture->MipsSamplerFilter = TF_Trilinear;
        WindowReflectionTexture->Init(128, PF_FloatRGBA);
        WindowReflectionTexture->UpdateResourceImmediate();
        WindowReflectionCapture = NewObject<USceneCaptureComponentCube>(this);
        WindowReflectionCapture->TextureTarget = WindowReflectionTexture;
        // SceneColor HDR has no exposure/tonemapping; the window's main view supplies them once.
        WindowReflectionCapture->CaptureSource = SCS_SceneColorHDRNoAlpha;
        WindowReflectionCapture->bCaptureEveryFrame = false;
        WindowReflectionCapture->bCaptureOnMovement = false;
        WindowReflectionCapture->bAlwaysPersistRenderingState = true;
        WindowReflectionCapture->bUseRayTracingIfEnabled = true;
        WindowReflectionCapture->PostProcessSettings.bOverride_DynamicGlobalIlluminationMethod = true;
        WindowReflectionCapture->PostProcessSettings.DynamicGlobalIlluminationMethod = EDynamicGlobalIlluminationMethod::Lumen;
        WindowReflectionCapture->PostProcessSettings.bOverride_ReflectionMethod = true;
        WindowReflectionCapture->PostProcessSettings.ReflectionMethod = EReflectionMethod::None;
        // ponytail: one local cube approximates parallax; native Lumen supplies precise nearby reflections.
        const FVector CapturePosition = Camera->GetActorLocation() + Camera->GetActorForwardVector() * 500.f - FVector::UpVector * 500.f;
        WindowReflectionCapture->SetWorldLocation(CapturePosition);
        if (WindowFrame) WindowReflectionCapture->HiddenActors.Add(WindowFrame.Get());
        WindowReflectionCapture->RegisterComponent();
        WindowReflectionCapture->SetComponentTickEnabled(false);
        for (UMaterialInstanceDynamic* Material : Materials)
        {
            UTexture* ExistingTexture = nullptr;
            if (!Material->GetTextureParameterValue(FMaterialParameterInfo(TEXT("LocalWindowReflection")), ExistingTexture)) continue;
            Material->SetTextureParameterValue(TEXT("LocalWindowReflection"), WindowReflectionTexture);
            Material->SetVectorParameterValue(TEXT("LocalWindowCapturePosition"), FLinearColor(CapturePosition.X, CapturePosition.Y, CapturePosition.Z, 1.f));
            Material->SetScalarParameterValue(TEXT("LocalWindowReflectionReady"), 0.f);
        }
    }
    RegisterCommands();
    if (!bTestMode || FParse::Param(FCommandLine::Get(), TEXT("OOWTestDesktop")) || FParse::Param(FCommandLine::Get(), TEXT("OOWTestDesktopInput")))
    {
        Desktop = MakeUnique<FWindowDesktop>(); Desktop->Initialize(this);
    }
    MakeInterface();
    SkySampling = FSceneViewExtensions::NewExtension<FWindowSkySampling>(GetWorld());
    OOWQuality(Session.Quality);

    float StartHour;
    int32 StartQuality;
    FString StartWeather;
    if (FParse::Value(FCommandLine::Get(), TEXT("OOWTime="), StartHour)) OOWTime(StartHour);
    if (FParse::Value(FCommandLine::Get(), TEXT("OOWWeather="), StartWeather)) OOWWeather(StartWeather);
    if (FParse::Value(FCommandLine::Get(), TEXT("OOWTestHour="), StartHour)) OOWTime(StartHour);
    if (FParse::Value(FCommandLine::Get(), TEXT("OOWTestWeather="), StartWeather)) OOWWeather(StartWeather);
    float TestCloudCover;
    if (bTestMode && FParse::Value(FCommandLine::Get(), TEXT("OOWTestCloudCover="), TestCloudCover) && FMath::IsFinite(TestCloudCover))
    {
        Session.CloudCover = FMath::Clamp(TestCloudCover, 0.f, 100.f);
        Session.Weather = TEXT("real");
    }
    float TestPrecipitation;
    if (bTestMode && FParse::Value(FCommandLine::Get(), TEXT("OOWTestPrecipitation="), TestPrecipitation) && FMath::IsFinite(TestPrecipitation) && TestPrecipitation >= 0.f)
    {
        Session.Precipitation = TestPrecipitation;
        Session.Weather = TEXT("real");
        Session.WeatherCode = 61;
    }
    int32 TestWeatherCode;
    if (bTestMode && FParse::Value(FCommandLine::Get(), TEXT("OOWTestWeatherCode="), TestWeatherCode))
    {
        Session.WeatherCode = TestWeatherCode;
        Session.Weather = TEXT("real");
    }
    if (FParse::Value(FCommandLine::Get(), TEXT("OOWTestQuality="), StartQuality)) OOWQuality(StartQuality);
    FString ExpectedScene;
    if (FParse::Value(FCommandLine::Get(), TEXT("OOWTestScene="), ExpectedScene) && !Session.Scene.Equals(ExpectedScene, ESearchCase::IgnoreCase))
        UE_LOG(LogTemp, Error, TEXT("OOW test expected scene %s but loaded %s"), *ExpectedScene, *Session.Scene);
    if (!Session.bHasWeather || Session.bRefreshPending) RefreshWeather();
    if (FParse::Param(FCommandLine::Get(), TEXT("OOWAudit")))
    {
        FTimerHandle Handle;
        GetWorldTimerManager().SetTimer(Handle, this, &AWindowDirector::OOWAudit, 12.f, false);
    }
    FastLightingUntil = GetWorld()->GetTimeSeconds() + 4;
    Precipitation = GetWorld()->SpawnActor<AWindowPrecipitation>();
    if (Precipitation && Camera) Precipitation->SetView(Camera->GetActorLocation(), Camera->GetActorForwardVector());
    if (Session.Scene == TEXT("Alley") && Camera)
    {
        Birds = GetWorld()->SpawnActor<AWindowBirds>();
        if (Birds) Birds->SetView(Camera->GetActorLocation(), Camera->GetActorForwardVector());
    }
    if (bTestMode)
    {
        TestStartedAt = GetWorld()->GetTimeSeconds();
        IFileManager::Get().MakeDirectory(*FPaths::GetPath(CapturePath), true);
        ScreenshotHandle = FScreenshotRequest::OnScreenshotRequestProcessed().AddWeakLambda(this, [this]
        {
            if (!bCaptureRequested) return;
            if (++CapturedFrames < CaptureFrames)
            {
                bCaptureRequested = false;
                TestStartedAt = GetWorld()->GetTimeSeconds() - TestSeconds + CaptureInterval;
            }
            else { OOWAudit(); ExitFrames = 6; }
        });
    }
    UpdateAudio();
}

void AWindowDirector::FindSceneActors()
{
    TMap<UMaterialInterface*, UMaterialInstanceDynamic*> SharedMaterials;
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        AActor* Actor = *It;
        if (Actor == this) continue;
        for (const FName& Tag : Actor->Tags)
        {
            const FString Name = Tag.ToString();
            if (!Name.StartsWith(TEXT("OOWCar_"))) continue;
            const int32 Car = FCString::Atoi(*Name.RightChop(7));
            CarParts.Add({ Actor, Actor->GetActorLocation(), Actor->GetActorRotation(), Car });
            CarOrigins.FindOrAdd(Car, Actor->GetActorLocation());
            Traffic.Add(Car, CarOrigins[Car]);
        }
        if (Actor->ActorHasTag(TEXT("OOWCamera"))) Camera = Cast<ACameraActor>(Actor);
        if (Actor->ActorHasTag(TEXT("OOWSun"))) Sun = Actor->FindComponentByClass<UDirectionalLightComponent>();
        if (Actor->ActorHasTag(TEXT("OOWNightLight")))
        {
            if (ULightComponent* Light = Actor->FindComponentByClass<ULightComponent>())
            {
                NightLights.Add(Light);
                NightLightIntensities.Add(Light->Intensity);
            }
        }
        if (Actor->ActorHasTag(TEXT("OOWSky"))) Sky = Actor->FindComponentByClass<USkyLightComponent>();
        if (Actor->ActorHasTag(TEXT("OOWAtmosphere"))) Atmosphere = Actor->FindComponentByClass<USkyAtmosphereComponent>();
        if (Actor->ActorHasTag(TEXT("OOWFog"))) Fog = Actor->FindComponentByClass<UExponentialHeightFogComponent>();
        if (Actor->ActorHasTag(TEXT("OOWCloud"))) Cloud = Actor->FindComponentByClass<UVolumetricCloudComponent>();
        if (Actor->ActorHasTag(TEXT("OOWPostProcess"))) PostProcess = Cast<APostProcessVolume>(Actor);
        TInlineComponentArray<UMeshComponent*> Meshes;
        Actor->GetComponents(Meshes);
        for (UMeshComponent* Mesh : Meshes)
        {
            for (int32 Index = 0; Index < Mesh->GetNumMaterials(); ++Index)
            {
                UMaterialInterface* Original = Mesh->GetMaterial(Index);
                if (!Original) continue;
                UMaterialInstanceDynamic** Existing = SharedMaterials.Find(Original);
                UMaterialInstanceDynamic* Dynamic = Existing ? *Existing : UMaterialInstanceDynamic::Create(Original, this);
                if (!Existing) { SharedMaterials.Add(Original, Dynamic); Materials.Add(Dynamic); }
                Mesh->SetMaterial(Index, Dynamic);
            }
        }
    }
    if (!Camera) MissingTags.Add(TEXT("OOWCamera"));
    if (!Sun) MissingTags.Add(TEXT("OOWSun"));
    if (!Sky) MissingTags.Add(TEXT("OOWSky"));
    if (!Atmosphere) MissingTags.Add(TEXT("OOWAtmosphere"));
    if (!Fog) MissingTags.Add(TEXT("OOWFog"));
    if (!Cloud) MissingTags.Add(TEXT("OOWCloud"));
    if (!PostProcess) MissingTags.Add(TEXT("OOWPostProcess"));
    if (Fog) BaseFogDensity = Fog->FogDensity;
    if (Atmosphere)
    {
        BaseRayleighScattering = Atmosphere->RayleighScatteringScale;
        BaseMieScattering = Atmosphere->MieScatteringScale;
        BaseMieAbsorption = Atmosphere->MieAbsorptionScale;
    }
    if (Sun)
    {
        const FString Prefix = TEXT("OOWSunAzimuth_");
        bSunSweep = Sun->GetOwner()->ActorHasTag(TEXT("OOWSunSweep"));
        for (const FName& Tag : Sun->GetOwner()->Tags)
        {
            const FString Name = Tag.ToString();
            if (Name.StartsWith(Prefix)) SunAzimuth = FCString::Atof(*Name.RightChop(Prefix.Len()));
        }
    }
    if (Camera)
    {
        for (const FName& Tag : Camera->Tags)
        {
            const FString Name = Tag.ToString();
            if (Name.StartsWith(TEXT("VerticalFov_"))) VerticalFov = FCString::Atof(*Name.RightChop(12));
        }
    }
    if (Sun)
    {
        Sun->SetMobility(EComponentMobility::Movable);
        Sun->SetAtmosphereSunLight(true);
        Sun->bCastCloudShadows = true;
        Sun->CloudShadowMapResolutionScale = .5f;
        Sun->CloudShadowExtent = 8.f;
        Sun->MarkRenderStateDirty();
    }
    if (Sky) { Sky->SetMobility(EComponentMobility::Movable); Sky->SetRealTimeCapture(true); }
    if (Cloud && Cloud->Material.LoadSynchronous())
    {
        CloudMaterial = UMaterialInstanceDynamic::Create(Cloud->Material.Get(), this);
        Cloud->SetMaterial(CloudMaterial);
        // The engine preset spans 256 km and starts 5 km up: too distant for
        // these low-angle window views. Keep the native temporally reconstructed clouds.
        CloudMaterial->SetScalarParameterValue(TEXT("Layout_CloudGlobalScale"), 32.f);
        // Native wind multiplies total shader time; keep it constant for gentle
        // erosion and integrate weather wind separately so direction changes cannot jump clouds.
        CloudMaterial->SetVectorParameterValue(TEXT("Layout_WindControls"), FLinearColor(.3f, .2f, .02f, .18f));
        CloudMaterial->SetVectorParameterValue(TEXT("Storm_LightningColor"), FLinearColor::Black);
        CloudMaterial->SetVectorParameterValue(TEXT("Storm_AlbedoColor"), FLinearColor(.52f, .55f, .58f, 1.f / 3.f));
        Cloud->SetTracingStartMaxDistance(80.f);
        Cloud->SetTracingMaxDistance(25.f);
        Cloud->SetReflectionViewSampleCountScale(.15f);
        Cloud->SetShadowViewSampleCountScale(.5f);
        Cloud->SetShadowReflectionViewSampleCountScale(.1f);
    }
    if (PostProcess)
    {
        PostProcess->Settings.bOverride_LumenSceneLightingUpdateSpeed = true;
        PostProcess->Settings.bOverride_LumenFinalGatherLightingUpdateSpeed = true;
    }
    for (const FString& Tag : MissingTags) UE_LOG(LogTemp, Warning, TEXT("OutOfWindow missing scene actor tag: %s"), *Tag);

}

void AWindowDirector::BindCamera()
{
    if (!Camera || bCameraBound) return;
    if (APlayerController* Controller = UGameplayStatics::GetPlayerController(this, 0))
    {
        Controller->bAutoManageActiveCameraTarget = false;
        Controller->SetViewTarget(Camera);
        Controller->SetIgnoreMoveInput(true);
        Controller->SetIgnoreLookInput(true);
        Controller->bShowMouseCursor = true;
        FInputModeGameAndUI InputMode;
        InputMode.SetHideCursorDuringCapture(false);
        InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
        Controller->SetInputMode(InputMode);
        bCameraBound = true;
    }
}

void AWindowDirector::RegisterCommands()
{
    auto Register = [this](const TCHAR* Name, TFunction<void(const TArray<FString>&)> Function)
    {
        Commands.Add(IConsoleManager::Get().RegisterConsoleCommand(Name, TEXT("Out of Window runtime control"),
            FConsoleCommandWithArgsDelegate::CreateWeakLambda(this, [Function = MoveTemp(Function)](const TArray<FString>& Args) { Function(Args); }), ECVF_Default));
    };
    Register(TEXT("OOWTime"), [this](const TArray<FString>& A) { if (A.Num()) OOWTime(FCString::Atof(*A[0])); });
    Register(TEXT("OOWWeather"), [this](const TArray<FString>& A) { if (A.Num()) OOWWeather(A[0]); });
    Register(TEXT("OOWScene"), [this](const TArray<FString>& A) { if (A.Num()) OOWScene(A[0]); });
    Register(TEXT("OOWQuality"), [this](const TArray<FString>& A) { if (A.Num()) OOWQuality(FCString::Atoi(*A[0])); });
    Register(TEXT("OOWFrame"), [this](const TArray<FString>& A) { if (A.Num()) OOWFrame(A[0]); });
    Register(TEXT("OOWAudit"), [this](const TArray<FString>&) { OOWAudit(); });
}

void AWindowDirector::OOWFrame(const FString& Style)
{
    if (WindowFrame && WindowFrame->SetStyle(FName(*Style))) Session.FrameStyle = WindowFrame->GetStyle().ToString();
}

void AWindowDirector::MakeInterface()
{
    if (!GEngine || !GEngine->GameViewport) return;
    const FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), 13);
    const FLinearColor Ink(.96f, .97f, .95f), Muted(.92f, .95f, .93f, .58f), Accent(.74f, .90f, .78f);
    const FSlateFontInfo SmallFont = FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), 8);
    static const FSlateRoundedBoxBrush PanelBrush(FLinearColor(FColor(12, 22, 28, 163)), 22.f, FLinearColor(1, 1, 1, .13f), 1.f);
    static const FSlateRoundedBoxBrush SegmentBrush(FLinearColor(0, 0, 0, .18f), 10.f);
    static const FSlateRoundedBoxBrush SegmentActiveBrush(FLinearColor(1, 1, 1, .11f), 7.f);
    static const FSlateRoundedBoxBrush SceneBrush(FLinearColor(1, 1, 1, .035f), 12.f);
    static const FSlateRoundedBoxBrush SceneActiveBrush(FLinearColor(.68f, .85f, .73f, .10f), 12.f, FLinearColor(.76f, .90f, .80f, .40f), 1.f);
    static const FSlateRoundedBoxBrush LiveBrush(FLinearColor(1, 1, 1, .04f), FLinearColor(1, 1, 1, .13f), 1.f);
    static const FSlateRoundedBoxBrush LiveActiveBrush(FLinearColor(1, 1, 1, .04f), FLinearColor(.74f, .90f, .78f, .24f), 1.f);
    static const FSlateRoundedBoxBrush AmbientBrush(FLinearColor(.009f, .018f, .024f, .85f), FLinearColor(1, 1, 1, .13f), 1.f);
    static const FButtonStyle FlatStyle = FButtonStyle()
        .SetNormal(FSlateRoundedBoxBrush(FLinearColor::Transparent, 7.f))
        .SetHovered(FSlateRoundedBoxBrush(FLinearColor(1, 1, 1, .08f), 7.f))
        .SetPressed(FSlateRoundedBoxBrush(FLinearColor(1, 1, 1, .12f), 7.f))
        .SetNormalPadding(FMargin(0)).SetPressedPadding(FMargin(0));
    static const FButtonStyle QualityStyle = FButtonStyle(FlatStyle)
        .SetNormal(FSlateRoundedBoxBrush(FLinearColor(.009f, .018f, .024f), 7.f, FLinearColor(1, 1, 1, .13f), 1.f))
        .SetHovered(FSlateRoundedBoxBrush(FLinearColor(.025f, .037f, .045f), 7.f, FLinearColor(1, 1, 1, .22f), 1.f))
        .SetPressed(FSlateRoundedBoxBrush(FLinearColor(.015f, .027f, .033f), 7.f, FLinearColor(.74f, .90f, .78f, .3f), 1.f));
    static const FComboButtonStyle MenuStyle = FComboButtonStyle(FCoreStyle::Get().GetWidgetStyle<FComboButtonStyle>("ComboButton"))
        .SetButtonStyle(QualityStyle).SetContentPadding(FMargin(10, 6))
        .SetMenuBorderBrush(FSlateNoResource()).SetMenuBorderPadding(0);
    static const FButtonStyle SceneButtonStyle = FButtonStyle(FlatStyle)
        .SetHovered(FSlateRoundedBoxBrush(FLinearColor(1, 1, 1, .08f), 12.f))
        .SetPressed(FSlateRoundedBoxBrush(FLinearColor(1, 1, 1, .12f), 12.f));
    static const FButtonStyle PillButtonStyle = FButtonStyle(FlatStyle)
        .SetHovered(FSlateRoundedBoxBrush(FLinearColor(1, 1, 1, .08f)))
        .SetPressed(FSlateRoundedBoxBrush(FLinearColor(1, 1, 1, .12f)));
    static const FSliderStyle TimeSliderStyle = FSliderStyle()
        .SetNormalBarImage(FSlateNoResource()).SetHoveredBarImage(FSlateNoResource()).SetDisabledBarImage(FSlateNoResource())
        .SetNormalThumbImage(FSlateRoundedBoxBrush(FLinearColor(.84f, .67f, .47f), 6.5f, FLinearColor::White, 2.f, FVector2D(13, 13)))
        .SetHoveredThumbImage(FSlateRoundedBoxBrush(FLinearColor(.90f, .74f, .54f), 6.5f, FLinearColor::White, 2.f, FVector2D(13, 13)))
        .SetDisabledThumbImage(FSlateNoResource()).SetBarThickness(3);
    static const TArray<TSharedPtr<FSlateDynamicImageBrush>> ScenePreviews = []
    {
        TArray<TSharedPtr<FSlateDynamicImageBrush>> Brushes;
        const TCHAR* Files[] = { TEXT("city.jpg"), TEXT("alley.jpg"), TEXT("village.png"), TEXT("forest.png"), TEXT("coast.png") };
        for (int32 Index = 0; Index < 5; ++Index)
        {
            const bool bUrban = Index < 2;
            const FVector2D Size = bUrban ? FVector2D(48, 36) : FVector2D(32, 32);
            auto Brush = MakeShared<FSlateDynamicImageBrush>(FName(*FPaths::Combine(FPaths::ProjectContentDir(), TEXT("Slate/ScenePreviews"), Files[Index])), Size);
            Brush->DrawAs = ESlateBrushDrawType::RoundedBox;
            Brush->OutlineSettings = FSlateBrushOutlineSettings(8.f);
            const float VisibleWidth = bUrban ? (48.f / 36.f) / (320.f / 178.f) : 941.f / 1672.f;
            Brush->SetUVRegion(FBox2f(FVector2f((1.f - VisibleWidth) / 2.f, 0), FVector2f((1.f + VisibleWidth) / 2.f, 1)));
            Brushes.Add(Brush);
        }
        return Brushes;
    }();
    TSharedRef<SVerticalBox> SceneButtons = SNew(SVerticalBox);
    const TCHAR* SceneKeys[] = { TEXT("City"), TEXT("Alley"), TEXT("Village"), TEXT("Forest"), TEXT("Coast") };
    const TCHAR* SceneNames[] = { TEXT("都市"), TEXT("后巷"), TEXT("村庄"), TEXT("山林"), TEXT("海滨") };
    const TCHAR* SceneDescriptions[] = { TEXT("街区与天际线"), TEXT("雨篷与石板路"), TEXT("田野与炊烟"), TEXT("松涛与溪流"), TEXT("潮汐与暮光") };
    TSharedPtr<SHorizontalBox> SceneRow;
    for (int32 Index = 0; Index < 5; ++Index)
    {
        if (Index == 0 || Index == 2)
        {
            SceneRow = SNew(SHorizontalBox);
            SceneButtons->AddSlot().AutoHeight().Padding(0, Index == 2 ? 7 : 0, 0, 0)[SceneRow.ToSharedRef()];
        }
        const FString Key = SceneKeys[Index], Name = SceneNames[Index];
        SceneRow->AddSlot().FillWidth(1).Padding(Index == 0 || Index == 2 ? 0 : 7, 0, 0, 0)
            [SNew(SBorder).Padding(0).BorderImage_Lambda([Key] { return Session.Scene == Key ? &SceneActiveBrush : &SceneBrush; })
                [SNew(SButton).ButtonStyle(&SceneButtonStyle).ContentPadding(6).HAlign(HAlign_Fill)
                    .ToolTipText(FText::FromString(Name)).OnClicked_Lambda([this, Key] { OOWScene(Key); return FReply::Handled(); })
                    [SNew(SHorizontalBox)
                        + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[SNew(SImage).Image(ScenePreviews[Index].Get())]
                        + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center).Padding(9, 0, 0, 0)
                            [SNew(SVerticalBox)
                                + SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).Text(FText::FromString(Name)).Font(SmallFont).ColorAndOpacity(Ink)]
                                + SVerticalBox::Slot().AutoHeight().Padding(0, 3, 0, 0)[SNew(STextBlock).Text(FText::FromString(SceneDescriptions[Index])).Font(FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), 6)).ColorAndOpacity(Muted)]]]]];
    }
    TSharedRef<SHorizontalBox> WeatherButtons = SNew(SHorizontalBox);
    const TCHAR* WeatherKeys[] = { TEXT("real"), TEXT("clear"), TEXT("cloudy"), TEXT("overcast"), TEXT("rain"), TEXT("snow"), TEXT("fog") };
    const TCHAR* WeatherNames[] = { TEXT("实时"), TEXT("晴"), TEXT("多云"), TEXT("阴"), TEXT("雨"), TEXT("雪"), TEXT("雾") };
    for (int32 Index = 0; Index < UE_ARRAY_COUNT(WeatherKeys); ++Index)
    {
        const FString Key = WeatherKeys[Index], Name = WeatherNames[Index];
        const auto IsSelected = [this, Key] { return Session.Weather == TEXT("real") ? Key == TEXT("real") : ActualWeather() == Key; };
        WeatherButtons->AddSlot().FillWidth(1)
            [SNew(SBorder).Padding(0).BorderImage_Lambda([IsSelected]() -> const FSlateBrush* { return IsSelected() ? &SegmentActiveBrush : FCoreStyle::Get().GetBrush(TEXT("NoBrush")); })
                [SNew(SButton).ButtonStyle(&FlatStyle).ContentPadding(FMargin(3, 6)).HAlign(HAlign_Center).ToolTipText(FText::FromString(Name))
                    .OnClicked_Lambda([this, Key] { OOWWeather(Key); return FReply::Handled(); })
                    [SNew(STextBlock).Text(FText::FromString(Name)).Font(SmallFont).ColorAndOpacity_Lambda([IsSelected, Ink, Muted] { return IsSelected() ? Ink : Muted; })]]];
    }
    TSharedRef<SHorizontalBox> PrecipitationButtons = SNew(SHorizontalBox);
    for (const FString Level : { TEXT("light"), TEXT("moderate"), TEXT("heavy") })
    {
        const auto Mode = [this, Level] { return Level + TEXT("_") + ActualWeather(); };
        PrecipitationButtons->AddSlot().FillWidth(1)
            [SNew(SBorder).Padding(0).BorderImage_Lambda([Mode]() -> const FSlateBrush* { return Session.Weather == Mode() ? &SegmentActiveBrush : FCoreStyle::Get().GetBrush(TEXT("NoBrush")); })
                [SNew(SButton).ButtonStyle(&FlatStyle).ContentPadding(6).HAlign(HAlign_Center)
                    .OnClicked_Lambda([this, Mode] { OOWWeather(Mode()); return FReply::Handled(); })
                    [SNew(STextBlock).Text_Lambda([Mode] { return FText::FromString(WindowWeather::LabelForCode(WindowWeather::CodeForPreview(Mode()))); })
                        .Font(SmallFont).ColorAndOpacity(Ink)]]];
    }
    TSharedRef<SComboButton> QualityMenu = SNew(SComboButton).ComboButtonStyle(&MenuStyle).ForegroundColor(Ink)
        .ToolTipText(FText::FromString(TEXT("画质")))
        .OnGetMenuContent_Lambda([this, SmallFont, Ink]() -> TSharedRef<SWidget>
        {
            TSharedRef<SVerticalBox> Options = SNew(SVerticalBox);
            const TCHAR* Names[] = { TEXT("节能"), TEXT("均衡"), TEXT("精细") };
            for (int32 Index = 0; Index < 3; ++Index)
            {
                Options->AddSlot().AutoHeight()
                    [SNew(SButton).ButtonStyle(&FlatStyle).ContentPadding(FMargin(12, 7)).HAlign(HAlign_Fill)
                        .OnClicked_Lambda([this, Index] { OOWQuality(Index); FSlateApplication::Get().DismissAllMenus(); return FReply::Handled(); })
                        [SNew(STextBlock).Text(FText::FromString(Names[Index])).Font(SmallFont).ColorAndOpacity(Ink)]];
            }
            return SNew(SBorder).BorderImage(&QualityStyle.Normal).Padding(3)[Options];
        })
        .ButtonContent()
        [SNew(STextBlock).Text_Lambda([] { return FText::FromString(Session.Quality == 0 ? TEXT("节能") : Session.Quality == 1 ? TEXT("均衡") : TEXT("精细")); }).Font(SmallFont).ColorAndOpacity(Ink)];
    TSharedRef<SComboButton> LocationMenu = SNew(SComboButton).ComboButtonStyle(&MenuStyle).ForegroundColor(Ink)
        .MenuPlacement(MenuPlacement_AboveRightAnchor)
        .OnGetMenuContent_Lambda([this, SmallFont, Ink, Muted]() -> TSharedRef<SWidget>
        {
            const auto Follow = SNew(SCheckBox).IsChecked(Session.bFollowIP ? ECheckBoxState::Checked : ECheckBoxState::Unchecked)
                [SNew(STextBlock).Text(FText::FromString(TEXT("跟随 IP 位置（可能不准确）"))).Font(SmallFont).ColorAndOpacity(Ink)];
            const auto City = SNew(SEditableTextBox).Text(FText::FromString(Session.ManualCity)).HintText(FText::FromString(TEXT("位置名称")));
            const auto Draft = MakeShared<FVector3d>(Session.ManualLatitude, Session.ManualLongitude, Session.ManualUtcOffset);
            auto NumberInput = [Draft](int32 Index, double Min, double Max)
            {
                return SNew(SNumericEntryBox<double>).MinValue(Min).MaxValue(Max)
                    .Value_Lambda([Draft, Index]() -> TOptional<double> { return (*Draft)[Index]; })
                    .OnValueChanged_Lambda([Draft, Index](double Value) { (*Draft)[Index] = Value; })
                    .OnValueCommitted_Lambda([Draft, Index](double Value, ETextCommit::Type) { (*Draft)[Index] = Value; });
            };
            const auto Latitude = NumberInput(0, -90, 90);
            const auto Longitude = NumberInput(1, -180, 180);
            const auto Offset = NumberInput(2, -12, 14);
            auto Row = [SmallFont, Muted](const TCHAR* Name, TSharedRef<SWidget> Input) -> TSharedRef<SWidget>
            {
                return SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)[SNew(STextBlock).Text(FText::FromString(Name)).Font(SmallFont).ColorAndOpacity(Muted)]
                    + SHorizontalBox::Slot().FillWidth(2)[Input];
            };
            return SNew(SBox).WidthOverride(310)
                [SNew(SBorder).BorderImage(&QualityStyle.Normal).Padding(12)
                    [SNew(SVerticalBox)
                        + SVerticalBox::Slot().AutoHeight()[Follow]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 10)
                            [SNew(SVerticalBox).IsEnabled_Lambda([Follow] { return !Follow->IsChecked(); })
                                + SVerticalBox::Slot().AutoHeight().Padding(0, 3)[Row(TEXT("位置名称"), City)]
                                + SVerticalBox::Slot().AutoHeight().Padding(0, 3)[Row(TEXT("纬度（北正南负）"), Latitude)]
                                + SVerticalBox::Slot().AutoHeight().Padding(0, 3)[Row(TEXT("经度（东正西负）"), Longitude)]
                                + SVerticalBox::Slot().AutoHeight().Padding(0, 3)[Row(TEXT("离线 UTC 时差"), Offset)]]
                        + SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).Text(FText::FromString(TEXT("未勾选时使用手动位置，不请求 IP 定位。\n联网后自动校准当地时区；设置保存在本机。"))).Font(SmallFont).ColorAndOpacity(Muted)]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 10, 0, 0)
                            [SNew(SButton).ButtonStyle(&QualityStyle).ContentPadding(FMargin(12, 7)).HAlign(HAlign_Center).VAlign(VAlign_Center)
                                .IsEnabled_Lambda([Draft] { return ValidLocation(Draft->X, Draft->Y, Draft->Z); })
                                .OnClicked_Lambda([this, Follow, City, Draft]
                                {
                                    ApplyLocation(Follow->IsChecked(), Draft->X, Draft->Y, City->GetText().ToString(), Draft->Z);
                                    FSlateApplication::Get().DismissAllMenus();
                                    return FReply::Handled();
                                })
                                [SNew(STextBlock).Text(FText::FromString(TEXT("保存并更新天气"))).Font(SmallFont).ColorAndOpacity(Ink)]]]];
        })
        .ButtonContent()[SNew(STextBlock).Text_Lambda([] { return FText::FromString(Session.bFollowIP ? TEXT("IP 近似定位") : TEXT("手动指定位置")); }).Font(SmallFont).ColorAndOpacity(Ink)];
    TSharedRef<SHorizontalBox> FrameButtons = SNew(SHorizontalBox);
    const TCHAR* FrameKeys[] = { TEXT("oak"), TEXT("ivory"), TEXT("graphite") };
    const TCHAR* FrameNames[] = { TEXT("烟熏橡木"), TEXT("象牙白"), TEXT("石墨灰") };
    for (int32 Index = 0; Index < 3; ++Index)
    {
        const FString Key = FrameKeys[Index], Name = FrameNames[Index];
        FrameButtons->AddSlot().FillWidth(1)
            [SNew(SBorder).Padding(0).BorderImage_Lambda([Key]() -> const FSlateBrush* { return Session.FrameStyle == Key ? &SegmentActiveBrush : FCoreStyle::Get().GetBrush(TEXT("NoBrush")); })
                [SNew(SButton).ButtonStyle(&FlatStyle).ContentPadding(FMargin(6)).HAlign(HAlign_Center)
                    .OnClicked_Lambda([this, Key] { OOWFrame(Key); return FReply::Handled(); })
                    [SNew(STextBlock).Text(FText::FromString(Name)).Font(SmallFont).ColorAndOpacity_Lambda([Key, Ink, Muted] { return Session.FrameStyle == Key ? Ink : Muted; })]]];
    }
    TSharedRef<SHorizontalBox> TimeMarks = SNew(SHorizontalBox);
    for (int32 Index = 0; Index < 5; ++Index)
    {
        if (Index) TimeMarks->AddSlot().FillWidth(1)[SNew(SBox)];
        TimeMarks->AddSlot().AutoWidth()
            [SNew(STextBlock).Text(FText::FromString(FString::Printf(TEXT("%02d"), Index * 6))).Font(FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), 6)).ColorAndOpacity(FLinearColor(1, 1, 1, .33f))];
    }
    auto TitleButton = [this, Font](const TCHAR* Text, FName Action)
    {
        return SNew(SBox).WidthOverride(32).HeightOverride(32)
            [SNew(SButton).ButtonStyle(FCoreStyle::Get(), "NoBorder").ContentPadding(0).HAlign(HAlign_Center).VAlign(VAlign_Center)
                .OnClicked_Lambda([this, Action] { DesktopButton(Action); return FReply::Handled(); })
                [SNew(STextBlock).Text(FText::FromString(Text)).Font(Font).ColorAndOpacity(FLinearColor(.88f, .90f, .85f))]];
    };
    const TSharedRef<SWindowVisibilityButton> VisibilityButton = SNew(SWindowVisibilityButton)
        .AccessibleText(FText::FromString(TEXT("隐藏或显示界面，Esc 恢复")));
    VisibilityControl = VisibilityButton;
    if (bTestMode && FParse::Param(FCommandLine::Get(), TEXT("OOWTestHideUI"))) VisibilityButton->SetInterfaceHidden(true);
    RestoreInterface = [WeakButton = TWeakPtr<SWindowVisibilityButton>(VisibilityButton)]
    {
        if (const auto Button = WeakButton.Pin()) Button->SetInterfaceHidden(false);
    };
    const TSharedRef<SOverlay> Controls = SNew(SOverlay)
        .Visibility_Lambda([VisibilityButton] { return VisibilityButton->IsInterfaceHidden() ? EVisibility::Collapsed : EVisibility::SelfHitTestInvisible; })
        + SOverlay::Slot().VAlign(VAlign_Top).Padding(15)
        [SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush(TEXT("WhiteBrush"))).BorderBackgroundColor(FLinearColor(.02f, .03f, .03f, .85f)).Padding(10)
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)[SNew(STextBlock).Text(FText::FromString(TEXT("OUT OF WINDOW  ·  一扇会呼吸的窗"))).Font(Font)]
                + SHorizontalBox::Slot().AutoWidth()[SNew(SBox).WidthOverride(32).HeightOverride(32)]
                + SHorizontalBox::Slot().AutoWidth()[TitleButton(TEXT("—"), TEXT("Minimize"))]
                + SHorizontalBox::Slot().AutoWidth()
                    [SNew(SBox).WidthOverride(32).HeightOverride(32)
                        [SNew(SButton).ButtonStyle(FCoreStyle::Get(), "NoBorder").ContentPadding(0)
                            .ToolTipText_Lambda([this] { return FText::FromString(Desktop && Desktop->IsDesktopMode() ? TEXT("还原为窗口") : TEXT("最大化为动态桌面")); })
                            .OnClicked_Lambda([this] { DesktopButton(TEXT("Maximize")); return FReply::Handled(); })
                            [SNew(SImage).Image_Lambda([this] { const auto& Style = FCoreStyle::Get().GetWidgetStyle<FWindowStyle>("Window"); return Desktop && Desktop->IsDesktopMode() ? &Style.RestoreButtonStyle.Normal : &Style.MaximizeButtonStyle.Normal; })]]]
                + SHorizontalBox::Slot().AutoWidth()[TitleButton(TEXT("×"), TEXT("Close"))]]]
        + SOverlay::Slot().HAlign(HAlign_Right).VAlign(VAlign_Top).Padding(20, 86, 54, 20)
        [SNew(SVerticalBox)
            + SVerticalBox::Slot().AutoHeight()
            [SNew(SBorder).BorderImage(&PanelBrush).Padding(14, 11)
                [SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight()
                    [SNew(SHorizontalBox)
                        + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
                            [SNew(STextBlock).Text_Lambda([this] { return StatusText(); }).Font(Font).Justification(ETextJustify::Right).ShadowOffset(FVector2D(1, 1))]
                        + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(12, 0, 0, 0)
                            [SNew(SButton).ButtonStyle(&FlatStyle).ContentPadding(FMargin(9, 5)).ToolTipText(FText::FromString(TEXT("刷新天气")))
                                .OnClicked_Lambda([this] { RefreshWeather(); return FReply::Handled(); })
                                [SNew(STextBlock).Text(FText::FromString(TEXT("刷新"))).Font(SmallFont).ColorAndOpacity(Muted)]]]
                    + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Right).Padding(0, 6, 0, 0)
                    [SNew(STextBlock).Visibility_Lambda([this] { return bCollapsed || LastViewportSize.Y >= 760 ? EVisibility::HitTestInvisible : EVisibility::Collapsed; })
                        .Text_Lambda([] { return FText::FromString(FString::Printf(TEXT("%.0f FPS"), 1. / FMath::Max(.001, FApp::GetDeltaTime()))); }).Font(SmallFont).ColorAndOpacity(Muted)]
                    + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Right).Padding(0, 4, 0, 0)
                    [SNew(SBox).Visibility_Lambda([this] { return bPrivacyDismissed || (!bCollapsed && LastViewportSize.Y < 760) ? EVisibility::Collapsed : EVisibility::Visible; })
                        [SNew(SButton).ButtonStyle(&FlatStyle).ContentPadding(0).ToolTipText(FText::FromString(TEXT("关闭提示")))
                            .OnClicked_Lambda([this] { bPrivacyDismissed = true; return FReply::Handled(); })
                            [SNew(STextBlock).Text(FText::FromString(TEXT("IP 定位可能不准确，可在「地理位置」中修改  ×"))).Font(SmallFont).ColorAndOpacity(Muted)]]]]]
            + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Right).Padding(0, 22, 0, 0)
            [SNew(SBox).WidthOverride(300).Visibility_Lambda([this] { return bCollapsed || LastViewportSize.Y >= 860 ? EVisibility::HitTestInvisible : EVisibility::Collapsed; })
                [SNew(STextBlock).Text_Lambda([]
                {
                    const FString Text = Session.Scene == TEXT("City") ? TEXT("01 / 05  都市\n街区与天际线") : Session.Scene == TEXT("Alley") ? TEXT("02 / 05  后巷\n雨篷与石板路") : Session.Scene == TEXT("Village") ? TEXT("03 / 05  村庄\n田野与屋瓦") : Session.Scene == TEXT("Forest") ? TEXT("04 / 05  山林\n松涛与溪流") : TEXT("05 / 05  海滨\n潮汐与暮光");
                    return FText::FromString(Text);
                }).Font(FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), 22)).Justification(ETextJustify::Right).ShadowOffset(FVector2D(1, 2))]]]
        + SOverlay::Slot().HAlign(HAlign_Right).VAlign(VAlign_Bottom).Padding(20, 20, 54, 63)
        [SNew(SBox).WidthOverride(410)
            [SNew(SBackgroundBlur).BlurStrength(20).CornerRadius(FVector4(22, 22, 22, 22)).Padding(0).LowQualityFallbackBrush(&PanelBrush)
            [SNew(SBorder).BorderImage(&PanelBrush).Padding(16)
                [SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight()
                    [SNew(SHorizontalBox)
                        + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
                            [SNew(SVerticalBox)
                                + SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).Text(FText::FromString(TEXT("A T M O S P H E R E"))).Font(FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), 7)).ColorAndOpacity(FLinearColor(.89f, .93f, .91f, .48f))]
                                + SVerticalBox::Slot().AutoHeight().Padding(0, 3, 0, 0)[SNew(STextBlock).Text(FText::FromString(TEXT("此刻的窗外"))).Font(FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), 13)).ColorAndOpacity(Ink)]]
                        + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
                            [SNew(SBox).WidthOverride(34).HeightOverride(34)
                                [SNew(SButton).ButtonStyle(&FlatStyle).ContentPadding(0).HAlign(HAlign_Center).VAlign(VAlign_Center)
                                    .ToolTipText_Lambda([this] { return FText::FromString(bCollapsed ? TEXT("展开设置") : TEXT("折叠设置")); })
                                    .OnClicked_Lambda([this] { bCollapsed = !bCollapsed; return FReply::Handled(); })
                                    [SNew(SImage).Image(&FCoreStyle::Get().GetWidgetStyle<FComboButtonStyle>("ComboButton").DownArrowImage)
                                        .ColorAndOpacity(Muted).RenderTransformPivot(FVector2D(.5, .5))
                                        .RenderTransform_Lambda([this] { return FSlateRenderTransform(FQuat2D(bCollapsed ? PI : 0.f)); })]]]]
                    + SVerticalBox::Slot().AutoHeight()
                    [SNew(SVerticalBox).Visibility_Lambda([this] { return bCollapsed ? EVisibility::Collapsed : EVisibility::SelfHitTestInvisible; })
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 18, 0, 0)
                        [SNew(SHorizontalBox)
                            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[SNew(STextBlock).Text_Lambda([this] { return FText::FromString(ClockText().ToString().Left(5)); }).Font(FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), 24)).ColorAndOpacity(Ink)]
                            + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center).Padding(8, 0, 0, 0)[SNew(STextBlock).Text_Lambda([this] { return FText::FromString(ClockText().ToString().Mid(7)); }).Font(SmallFont).ColorAndOpacity(Muted)]
                            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
                            [SNew(SBorder).Padding(0).BorderImage_Lambda([] { return Session.bLiveTime ? &LiveActiveBrush : &LiveBrush; })
                                [SNew(SButton).ButtonStyle(&PillButtonStyle).ContentPadding(FMargin(11, 7))
                                    .OnClicked_Lambda([this] { Session.bLiveTime = !Session.bLiveTime; FastLightingUntil = GetWorld()->GetTimeSeconds() + 4; return FReply::Handled(); })
                                    [SNew(STextBlock).Text(FText::FromString(TEXT("●  跟随当地"))).Font(SmallFont).ColorAndOpacity_Lambda([Accent, Muted] { return Session.bLiveTime ? Accent : Muted; })]]]]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 10, 0, 0)
                        [SNew(SOverlay)
                            + SOverlay::Slot().VAlign(VAlign_Center).Padding(6.5f, 0)
                                [SNew(SBox).HeightOverride(3)[SNew(SComplexGradient).Orientation(Orient_Vertical)
                                    .GradientColors(TArray<FLinearColor>{ FLinearColor(FColor::FromHex(TEXT("0c1a32"))), FLinearColor(FColor::FromHex(TEXT("e7a86b"))), FLinearColor(FColor::FromHex(TEXT("e4dcc7"))), FLinearColor(FColor::FromHex(TEXT("d87f66"))), FLinearColor(FColor::FromHex(TEXT("0c1a32"))) })]]
                            + SOverlay::Slot()[SNew(SSlider).Style(&TimeSliderStyle).StepSize(1.f / 1439.f)
                                .Value_Lambda([] { return Session.Hour / (23.f + 59.f / 60.f); })
                                .OnValueChanged_Lambda([this](float Value) { OOWTime(FMath::RoundToFloat(Value * 1439.f) / 60.f); })]]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 7, 0, 15)[TimeMarks]
                        + SVerticalBox::Slot().AutoHeight()[SNew(SBox).HeightOverride(1)[SNew(SImage).Image(FCoreStyle::Get().GetBrush(TEXT("WhiteBrush"))).ColorAndOpacity(FLinearColor(1, 1, 1, .13f))]]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 13, 0, 0)
                        [SNew(SHorizontalBox)
                            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 14, 0)[SNew(STextBlock).Text(FText::FromString(TEXT("天气"))).Font(SmallFont).ColorAndOpacity(Muted)]
                            + SHorizontalBox::Slot().FillWidth(1)[SNew(SBorder).BorderImage(&SegmentBrush).Padding(3)[WeatherButtons]]]
                        + SVerticalBox::Slot().AutoHeight()
                        [SNew(SBorder).BorderImage(&SegmentBrush).Padding(3)
                            .Visibility_Lambda([this] { return Session.Weather != TEXT("real") && (ActualWeather() == TEXT("rain") || ActualWeather() == TEXT("snow")) ? EVisibility::Visible : EVisibility::Collapsed; })
                            [PrecipitationButtons]]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 12, 0, 0)
                        [SNew(SHorizontalBox)
                            + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)[SNew(STextBlock).Text(FText::FromString(TEXT("画质"))).Font(SmallFont).ColorAndOpacity(Muted)]
                            + SHorizontalBox::Slot().AutoWidth()[QualityMenu]]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 12, 0, 0)
                        [SNew(SHorizontalBox)
                            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 14, 0)[SNew(STextBlock).Text(FText::FromString(TEXT("窗框"))).Font(SmallFont).ColorAndOpacity(Muted)]
                            + SHorizontalBox::Slot().FillWidth(1)[SNew(SBorder).BorderImage(&SegmentBrush).Padding(3)[FrameButtons]]]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 12, 0, 0)
                        [SNew(SHorizontalBox)
                            + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)[SNew(STextBlock).Text(FText::FromString(TEXT("地理位置"))).Font(SmallFont).ColorAndOpacity(Muted)]
                            + SHorizontalBox::Slot().AutoWidth()[LocationMenu]]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 12, 0, 0)[SceneButtons]]]]]]
        + SOverlay::Slot().HAlign(HAlign_Right).VAlign(VAlign_Bottom).Padding(20, 20, 484, 63)
        [SNew(SBorder).BorderImage(&AmbientBrush).Padding(0)
            [SNew(SButton).ButtonStyle(&PillButtonStyle).ContentPadding(FMargin(15, 9)).OnClicked_Lambda([this] { ToggleAudio(); return FReply::Handled(); })
                [SNew(STextBlock).Text_Lambda([] { return FText::FromString(Session.bAudio ? TEXT("♫  环境声景") : TEXT("♪  环境声景")); }).Font(SmallFont).ColorAndOpacity_Lambda([Ink, Muted] { return Session.bAudio ? Ink : Muted; })]]];
    Interface = SNew(SOverlay)
        + SOverlay::Slot()[Controls]
        + SOverlay::Slot().HAlign(HAlign_Right).VAlign(VAlign_Top).Padding(0, 25, 121, 0)[VisibilityButton];
    GEngine->GameViewport->AddViewportWidgetContent(Interface.ToSharedRef(), 10);
    FString CaptureMenu;
    if (bTestMode && FParse::Value(FCommandLine::Get(), TEXT("OOWTestMenu="), CaptureMenu))
    {
        const auto Menu = CaptureMenu == TEXT("location") ? LocationMenu : QualityMenu;
        GetWorld()->GetTimerManager().SetTimerForNextTick([Menu] { Menu->SetIsOpen(true, false); });
    }
}

FText AWindowDirector::StatusText() const
{
    const FDateTime Now = LocalNow();
    const TCHAR* Status = bFetching ? TEXT("正在同步所选位置的天气") : Session.bFallback ? TEXT("离线天气示例 · 非实时") : Session.bFollowIP ? TEXT("实时天空 · IP 近似位置") : TEXT("实时天空 · 手动位置");
    return FText::FromString(FString::Printf(TEXT("%s\n%s  %.0f°C\n%s · 风 %.0f km/h · %02d:%02d"), Status, *Session.City, Session.Temperature, WindowWeather::LabelForCode(ActiveWeatherCode()), Session.WindSpeed, Now.GetHour(), Now.GetMinute()));
}

FText AWindowDirector::ClockText() const
{
    const int32 Minutes = FMath::RoundToInt(Session.Hour * 60) % 1440;
    const TCHAR* Period = SolarElevation < -6 ? (Session.Hour < 5 ? TEXT("深夜") : TEXT("夜晚")) : SolarElevation < 6 ? (SolarMinutes < 720 ? TEXT("晨曦") : TEXT("暮色")) : SolarElevation < 12 ? (SolarMinutes < 720 ? TEXT("清晨") : TEXT("黄昏")) : Session.Hour < 11 ? TEXT("上午") : Session.Hour < 14 ? TEXT("日中") : TEXT("午后");
    return FText::FromString(FString::Printf(TEXT("%02d:%02d  %s"), Minutes / 60, Minutes % 60, Period));
}

void AWindowDirector::DesktopButton(FName Action)
{
    if (DesktopAction) DesktopAction(Action);
}

FString AWindowDirector::ActualWeather() const { return WindowWeather::FamilyForCode(ActiveWeatherCode()); }

void AWindowDirector::OOWTime(float Hour)
{
    if (!FMath::IsFinite(Hour)) return;
    const float NewHour = FMath::Fmod(FMath::Fmod(Hour, 24.f) + 24.f, 24.f);
    if (!FMath::IsNearlyEqual(NewHour, Session.Hour)) FastLightingUntil = GetWorld()->GetTimeSeconds() + 3;
    Session.Hour = NewHour;
    Session.bLiveTime = false;
}

void AWindowDirector::OOWWeather(const FString& Mode)
{
    const FString Normalized = WindowWeather::NormalizeMode(Mode);
    if (Normalized.IsEmpty()) return;
    Session.Weather = Normalized;
    FastLightingUntil = GetWorld()->GetTimeSeconds() + 4;
}

void AWindowDirector::OOWScene(const FString& Scene)
{
    if (bChangingLevel) return;
    for (const TCHAR* Key : { TEXT("City"), TEXT("Alley"), TEXT("Village"), TEXT("Forest"), TEXT("Coast") })
    {
        if (!Scene.Equals(Key, ESearchCase::IgnoreCase) || Session.Scene == Key) continue;
        const FString MapPath = FString(TEXT("/Game/Maps/")) + Key;
        if (!FPackageName::DoesPackageExist(MapPath)) { UE_LOG(LogTemp, Error, TEXT("Scene map is missing: %s"), *MapPath); return; }
        Session.Wetness = Wetness;
        Session.Water = Water;
        Session.Scene = Key;
        bChangingLevel = true;
        UGameplayStatics::OpenLevel(this, FName(*MapPath));
        return;
    }
}

void AWindowDirector::OOWQuality(int32 Quality)
{
    Session.Quality = FMath::Clamp(Quality, 0, 2);
    if (UGameUserSettings* Settings = GEngine ? GEngine->GetGameUserSettings() : nullptr)
    {
        Settings->SetOverallScalabilityLevel(Session.Quality + 1);
        Settings->SetGlobalIlluminationQuality(FMath::Max(2, Session.Quality + 1));
        Settings->SetReflectionQuality(FMath::Max(2, Session.Quality + 1));
        Settings->SetResolutionScaleValueEx(Session.Quality == 0 ? 70.f : Session.Quality == 1 ? 85.f : 100.f);
        Settings->ApplyNonResolutionSettings();
    }
    SetCVar(TEXT("r.Lumen.DiffuseIndirect.Allow"), 1);
    // The GI quality 2 fallback washes out two-sided canvas and amplifies its wall bounce.
    SetCVar(TEXT("r.Lumen.ScreenProbeGather.TwoSidedFoliageBackfaceDiffuse"), 1);
    SetCVar(TEXT("r.Lumen.Reflections.Allow"), 1);
    SetCVar(TEXT("r.Lumen.TranslucencyReflections.FrontLayer.Enable"), Session.Quality > 0 ? 1 : 0);
    SetCVar(TEXT("r.Lumen.TranslucencyReflections.FrontLayer.Allow"), Session.Quality > 0 ? 1 : 0);
    SetCVar(TEXT("r.Lumen.HardwareRayTracing.LightingMode"), Session.Quality == 2 ? 2 : 0);
    SetCVar(TEXT("r.SkyLight.RealTimeReflectionCapture.TimeSlice"), 1);
    SetCVar(TEXT("r.VolumetricCloud"), 1);
    SetCVar(TEXT("r.VolumetricRenderTarget"), 1);
    // Mode 0 retains temporal reconstruction; Mode 1 amplified cloud shimmer in the A/B test.
    SetCVar(TEXT("r.VolumetricRenderTarget.Mode"), 0);
    SetCVar(TEXT("r.VolumetricCloud.DistanceToSampleMaxCount"), 5);
    UpdateCloudSampling(0.f);
}

void AWindowDirector::ApplyLocation(bool bFollowIP, double Latitude, double Longitude, const FString& City, double UtcOffset)
{
    if (!ValidLocation(Latitude, Longitude, UtcOffset)) return;
    // Unbind before cancellation so an old location cannot overwrite the new selection.
    for (auto Request : { GeoRequest, ForecastRequest })
        if (Request) { Request->OnProcessRequestComplete().Unbind(); Request->CancelRequest(); }
    bFetching = false;
    Session.bFollowIP = bFollowIP;
    Session.ManualLatitude = Latitude; Session.ManualLongitude = Longitude; Session.ManualUtcOffset = UtcOffset;
    Session.ManualCity = City.TrimStartAndEnd().Left(80);
    if (Session.ManualCity.IsEmpty()) Session.ManualCity = TEXT("手动位置");
    const TCHAR* Section = TEXT("OutOfWindow.Location");
    GConfig->SetBool(Section, TEXT("FollowIP"), bFollowIP, GGameUserSettingsIni);
    GConfig->SetString(Section, TEXT("City"), *Session.ManualCity, GGameUserSettingsIni);
    GConfig->SetDouble(Section, TEXT("Latitude"), Latitude, GGameUserSettingsIni);
    GConfig->SetDouble(Section, TEXT("Longitude"), Longitude, GGameUserSettingsIni);
    GConfig->SetDouble(Section, TEXT("UtcOffset"), UtcOffset, GGameUserSettingsIni);
    GConfig->Flush(false, GGameUserSettingsIni);
    RefreshWeather();
}

void AWindowDirector::RefreshWeather()
{
    if (bFetching || bTestMode) return;
    bFetching = true;
    Session.bRefreshPending = true;
    if (!Session.bFollowIP)
    {
        Session.City = Session.ManualCity;
        Session.Latitude = Session.ManualLatitude; Session.Longitude = Session.ManualLongitude;
        Session.OffsetSeconds = Session.ManualUtcOffset * 3600;
        Session.Timezone = TEXT("");
        FetchForecast(Session.Latitude, Session.Longitude, Session.City, Session.Timezone);
        return;
    }
    GeoRequest = FHttpModule::Get().CreateRequest();
    GeoRequest->SetURL(TEXT("https://ipwho.is/?fields=success,city,region,country,latitude,longitude,timezone"));
    GeoRequest->SetVerb(TEXT("GET"));
    GeoRequest->SetTimeout(8);
    GeoRequest->OnProcessRequestComplete().BindWeakLambda(this, [this](FHttpRequestPtr, FHttpResponsePtr Response, bool bSuccess)
    {
        TSharedPtr<FJsonObject> Json;
        bool bGeoOK = false;
        if (!ReadJson(Response, bSuccess, Json) || !Json->TryGetBoolField(TEXT("success"), bGeoOK) || !bGeoOK) { UseOfflineWeather(); return; }
        double Latitude = 0, Longitude = 0;
        if (!Json->TryGetNumberField(TEXT("latitude"), Latitude) || !Json->TryGetNumberField(TEXT("longitude"), Longitude) || !ValidLocation(Latitude, Longitude, 0)) { UseOfflineWeather(); return; }
        FString City = TEXT("IP 近似位置"), Timezone;
        Json->TryGetStringField(TEXT("city"), City);
        const TSharedPtr<FJsonObject>* Zone = nullptr;
        if (Json->TryGetObjectField(TEXT("timezone"), Zone))
        {
            (*Zone)->TryGetStringField(TEXT("id"), Timezone);
            Session.OffsetSeconds = Number(*Zone, TEXT("offset"), Session.OffsetSeconds);
        }
        FetchForecast(Latitude, Longitude, City, Timezone);
    });
    if (!GeoRequest->ProcessRequest()) UseOfflineWeather();
}

void AWindowDirector::FetchForecast(double Latitude, double Longitude, const FString& City, const FString& Timezone)
{
    Session.Latitude = Latitude; Session.Longitude = Longitude; Session.City = City; Session.Timezone = Timezone;
    ForecastRequest = FHttpModule::Get().CreateRequest();
    ForecastRequest->SetURL(FString::Printf(TEXT("https://api.open-meteo.com/v1/forecast?latitude=%.6f&longitude=%.6f&current=temperature_2m,apparent_temperature,is_day,precipitation,weather_code,cloud_cover,wind_speed_10m,wind_direction_10m,wind_gusts_10m&timezone=auto&forecast_days=1"), Latitude, Longitude));
    ForecastRequest->SetVerb(TEXT("GET"));
    ForecastRequest->SetTimeout(8);
    ForecastRequest->OnProcessRequestComplete().BindWeakLambda(this, [this, Latitude, Longitude, City, Timezone](FHttpRequestPtr, FHttpResponsePtr Response, bool bSuccess)
    {
        TSharedPtr<FJsonObject> Json;
        const TSharedPtr<FJsonObject>* Current = nullptr;
        if (!ReadJson(Response, bSuccess, Json) || !Json->TryGetObjectField(TEXT("current"), Current)) { UseOfflineWeather(); return; }
        Session.Latitude = Latitude;
        Session.Longitude = Longitude;
        Session.City = City;
        Session.Timezone = Timezone;
        Session.OffsetSeconds = Number(Json, TEXT("utc_offset_seconds"), Session.OffsetSeconds);
        Json->TryGetStringField(TEXT("timezone"), Session.Timezone);
        Session.Temperature = Number(*Current, TEXT("temperature_2m"), 22);
        const double Code = Number(*Current, TEXT("weather_code"), -1);
        Session.WeatherCode = Code >= 0 && Code <= 99 && FMath::FloorToDouble(Code) == Code ? static_cast<int32>(Code) : -1;
        Session.CloudCover = FMath::Clamp(Number(*Current, TEXT("cloud_cover"), 35), 0., 100.);
        Session.Precipitation = FMath::Max(0., Number(*Current, TEXT("precipitation"), 0));
        Session.WindSpeed = FMath::Clamp(Number(*Current, TEXT("wind_speed_10m"), 8), 0., 100.);
        Session.WindDirection = Number(*Current, TEXT("wind_direction_10m"), 240);
        Session.Gust = FMath::Clamp(Number(*Current, TEXT("wind_gusts_10m"), Session.WindSpeed), 0., 140.);
        Session.bHasWeather = true;
        Session.bFallback = false;
        Session.bRefreshPending = false;
        bFetching = false;
        FastLightingUntil = GetWorld()->GetTimeSeconds() + 4;
    });
    if (!ForecastRequest->ProcessRequest()) UseOfflineWeather();
}

void AWindowDirector::UseOfflineWeather()
{
    if (bTestMode)
    {
        Session.City = TEXT("上海"); Session.Timezone = TEXT("Asia/Shanghai");
        Session.Latitude = 31.23; Session.Longitude = 121.47; Session.OffsetSeconds = 28800;
    }
    Session.Temperature = 22; Session.CloudCover = 35; Session.WeatherCode = 1; Session.Precipitation = 0;
    Session.WindSpeed = 8; Session.Gust = 8; Session.WindDirection = 240;
    Session.bHasWeather = true; Session.bFallback = true; Session.bRefreshPending = false; bFetching = false;
    UE_LOG(LogTemp, Warning, TEXT("OutOfWindow uses offline example weather at %s"), *Session.City);
}

void AWindowDirector::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (bChangingLevel) return;
    BindCamera();
    if (Camera && VerticalFov > 0 && GEngine && GEngine->GameViewport)
    {
        FVector2D Size;
        GEngine->GameViewport->GetViewportSize(Size);
        if (Size.X > 0 && Size.Y > 0 && Size != LastViewportSize)
        {
            const float HorizontalFov = FMath::RadiansToDegrees(2 * FMath::Atan(FMath::Tan(FMath::DegreesToRadians(VerticalFov * .5f)) * Size.X / Size.Y));
            Camera->GetCameraComponent()->SetFieldOfView(HorizontalFov);
            // UE derives vertical FOV from this reference aspect as well. Keep it
            // in sync so MaintainYFOV does not apply a second, stale aspect correction.
            Camera->GetCameraComponent()->SetAspectRatio(Size.X / Size.Y);
            LastViewportSize = Size;
        }
    }
    if (Desktop) Desktop->Tick();
    if (Session.bLiveTime)
    {
        const FDateTime Now = LocalNow();
        Session.Hour = Now.GetHour() + Now.GetMinute() / 60.f + Now.GetSecond() / 3600.f;
    }
    ApplyLighting(FMath::Min(DeltaSeconds, .1f));
    UpdateCloudSampling(FMath::Min(DeltaSeconds, .1f));
    if (WindowFrame && Camera)
    {
        WindowFrame->FitToView(Camera->GetCameraComponent(), LastViewportSize.Y > 0 ? LastViewportSize.X / LastViewportSize.Y : Camera->GetCameraComponent()->AspectRatio);
        WindowFrame->SetDaylight(Daylight);
    }
    UpdateMaterials(DeltaSeconds);
    if (Birds)
    {
        const float Bearing = FMath::DegreesToRadians(Session.WindDirection);
        Birds->SetConditions(Daylight, ActualWeather() == TEXT("clear") || ActualWeather() == TEXT("cloudy"),
            FVector(-FMath::Sin(Bearing), FMath::Cos(Bearing), 0) * Session.WindSpeed / 3.6f * 100.f);
    }
    Traffic.Tick(DeltaSeconds, ActualWeather());
    for (const FCarPart& Part : CarParts)
    {
        if (!Part.Actor.IsValid()) continue;
        const FWindowTrafficCar* Car = Traffic.Cars.FindByPredicate([&Part](const FWindowTrafficCar& State) { return State.Id == Part.Car; });
        if (!Car) continue;
        const FVector Origin = CarOrigins[Part.Car];
        const FRotator Steering(0, FMath::FindDeltaAngleDegrees(Car->Direction < 0 ? 180.f : 0.f, Traffic.Yaw(*Car)), 0);
        Part.Actor->SetActorLocationAndRotation(Traffic.Location(*Car, Origin.Z) + Steering.RotateVector(Part.Origin - Origin),
            Steering + Part.Rotation);
    }
    if (Camera) Traffic.UpdateHeadlights(this, Camera->GetActorLocation(), 1.f - Daylight, DeltaSeconds);
    if (bTestMode)
    {
        const float Now = GetWorld()->GetTimeSeconds();
        bool bShadersCompiling = false;
#if WITH_EDITOR
        bShadersCompiling = GShaderCompilingManager && GShaderCompilingManager->IsCompiling();
#endif
        if (!bCaptureRequested && bShadersCompiling)
        {
            TestStartedAt = Now;
            FrameTimes.Reset();
            if (Birds && Camera) Birds->SetView(Camera->GetActorLocation(), Camera->GetActorForwardVector());
        }
        const float Elapsed = Now - TestStartedAt;
        if (!bShadersCompiling && Elapsed > 2) FrameTimes.Add(DeltaSeconds * 1000.f);
        if (!bCaptureRequested && !bShadersCompiling && Elapsed >= TestSeconds)
        {
            bCaptureRequested = true;
            const FString FramePath = CapturedFrames + 1 == CaptureFrames ? CapturePath
                : FPaths::ChangeExtension(CapturePath, TEXT("")) + FString::Printf(TEXT("-%03d.png"), CapturedFrames);
            FScreenshotRequest::RequestScreenshot(FramePath, FParse::Param(FCommandLine::Get(), TEXT("OOWCaptureUI")), false);
        }
        if (ExitFrames >= 0 && --ExitFrames <= 0) FPlatformMisc::RequestExit(false);
        if (Elapsed > TestSeconds + 35) { UE_LOG(LogTemp, Error, TEXT("OOW screenshot timeout")); OOWAudit(); FPlatformMisc::RequestExit(false); }
    }
    if (Session.bAudio && NoiseWave && NoiseWave->GetAvailableAudioByteCount() < 22050)
    {
        TArray<int16> Samples;
        Samples.SetNumUninitialized(22050);
        for (int16& Sample : Samples) Sample = static_cast<int16>(Random.RandRange(-12000, 12000));
        NoiseWave->QueueAudio(reinterpret_cast<const uint8*>(Samples.GetData()), Samples.Num() * sizeof(int16));
    }
}

void AWindowDirector::UpdateCloudSampling(float DeltaSeconds)
{
    if (!Cloud) return;
    FIntPoint RenderSize;
    if (SkySampling && SkySampling->GetMeasurement(VisibleSkyFraction, RenderSize))
        VisibleSkyPixels = VisibleSkyFraction * static_cast<double>(RenderSize.X) * RenderSize.Y;
    CloudTargetSampleScale = WindowCloudSampleScale(VisibleSkyPixels, Session.Quality, CloudSampleBudget.GetValueOnGameThread());
    CloudSampleScale = DeltaSeconds > 0 ? FMath::FInterpTo(CloudSampleScale, CloudTargetSampleScale, DeltaSeconds, .6f) : CloudTargetSampleScale;
    if (FMath::Abs(Cloud->ViewSampleCountScale - CloudSampleScale) > .02f)
        Cloud->SetViewSampleCountScale(CloudSampleScale);
}

void AWindowDirector::ApplyLighting(float DeltaSeconds)
{
    const FDateTime Date = LocalNow();
    const double YearDays = FDateTime::IsLeapYear(Date.GetYear()) ? 366. : 365.;
    const double Gamma = 2 * PI / YearDays * (Date.GetDayOfYear() - 1 + (Session.Hour - 12) / 24.);
    const double Decl = .006918 - .399912 * FMath::Cos(Gamma) + .070257 * FMath::Sin(Gamma) - .006758 * FMath::Cos(2 * Gamma) + .000907 * FMath::Sin(2 * Gamma) - .002697 * FMath::Cos(3 * Gamma) + .00148 * FMath::Sin(3 * Gamma);
    const double Equation = 229.18 * (.000075 + .001868 * FMath::Cos(Gamma) - .032077 * FMath::Sin(Gamma) - .014615 * FMath::Cos(2 * Gamma) - .040849 * FMath::Sin(2 * Gamma));
    SolarMinutes = Session.Hour * 60 + Equation + 4 * Session.Longitude - Session.OffsetSeconds / 60.;
    const double HourAngle = FMath::DegreesToRadians(SolarMinutes / 4 - 180);
    const double Latitude = FMath::DegreesToRadians(Session.Latitude);
    const double Elevation = FMath::Asin(FMath::Clamp(FMath::Sin(Latitude) * FMath::Sin(Decl) + FMath::Cos(Latitude) * FMath::Cos(Decl) * FMath::Cos(HourAngle), -1., 1.));
    SolarElevation = FMath::RadiansToDegrees(Elevation);
    Daylight = Smooth(-.12f, .18f, FMath::Sin(Elevation));
    const FString Weather = ActualWeather();
    float TargetCloudiness = Session.Weather == TEXT("real") ? Session.CloudCover / 100.f
        : Weather == TEXT("clear") ? .25f : Weather == TEXT("cloudy") ? .6f : Weather == TEXT("overcast") ? 1.f : .9f;
    if (Weather == TEXT("rain") || Weather == TEXT("snow")) TargetCloudiness = FMath::Max(TargetCloudiness, .96f);
    Cloudiness = FMath::FInterpTo(Cloudiness, TargetCloudiness, DeltaSeconds, .4f);
    const float CloudBlend = Smooth(.25f, .96f, Cloudiness);
    const float Glow = FMath::Exp(-FMath::Square(FMath::Sin(Elevation) / .22f));
    const float Elapsed = GetWorld()->GetTimeSeconds();
    if (Sun)
    {
        FVector Direction;
        if (bSunSweep && Camera)
        {
            FVector Right = Camera->GetActorRightVector(); Right.Z = 0; Right.Normalize();
            Direction = (Right * FMath::Lerp(-.95f, .95f, FMath::Clamp((Session.Hour - 6) / 12, 0.f, 1.f)) + FVector::UpVector * FMath::Sin(Elevation)).GetSafeNormal();
        }
        else
        {
            Direction = FVector(FMath::Sin(SunAzimuth) * FMath::Cos(Elevation), -FMath::Cos(SunAzimuth) * FMath::Cos(Elevation), FMath::Sin(Elevation));
        }
        Sun->GetOwner()->SetActorRotation(FMath::RInterpTo(Sun->GetOwner()->GetActorRotation(), (-Direction).Rotation(), DeltaSeconds, 3));
        // Cumulonimbus structure is a directional-light effect: a lit anvil over
        // a self-shadowed base. Cutting the sun 29x under full cover left only
        // ambient, which lit the deck isotropically and erased that gradient.
        const float TargetLux = 90000.f * Smooth(-.015f, .08f, FMath::Sin(Elevation)) * FMath::Lerp(.9f, .18f, CloudBlend);
        Sun->SetIntensity(FMath::FInterpTo(Sun->Intensity, TargetLux, DeltaSeconds, 2));
        Sun->SetLightColor(FMath::Lerp(FLinearColor(1.f, .94f, .86f), FLinearColor(1.f, .53f, .26f), Glow * .8f));
    }
    // Overcast diffuse light is several stops below a clear sky; the old .85
    // floor kept rainy days nearly as bright as fair weather.
    if (Sky) Sky->SetIntensity(FMath::FInterpTo(Sky->Intensity, (.07f + Daylight * .93f) * FMath::Lerp(1.f, .45f, CloudBlend), DeltaSeconds, 2));
    if (Atmosphere)
    {
        Atmosphere->SetRayleighScatteringScale(BaseRayleighScattering * FMath::Lerp(1.f, .35f, CloudBlend));
        // Mie is the aerosol term: a single-scatter lobe over the default profile,
        // no spatial structure. 2.1x was faking the overcast deck with it, which
        // is why the patch rendered as a flat white sheet -- it lays a uniform
        // veil over everything below the cloud and buries whatever structure the
        // deck has. Real 550nm AOD is ~0.1-0.2 and humidity growth is tens of
        // percent, so the honest overcast signal here is a modest scatter bump
        // plus enough absorption to keep the veil grey. The deck itself has to
        // come from cloud extinction, below.
        Atmosphere->SetMieScatteringScale(BaseMieScattering * FMath::Lerp(1.f, 1.25f, CloudBlend));
        Atmosphere->SetMieAbsorptionScale(BaseMieAbsorption * FMath::Lerp(1.f, 1.3f, CloudBlend));
    }
    for (int32 Index = 0; Index < NightLights.Num(); ++Index)
    {
        ULightComponent* Light = NightLights[Index];
        const float Fade = Light->GetOwner()->ActorHasTag(TEXT("OOWInteriorLight")) ? Smooth(.58f, .86f, 1.f - Daylight) : 1.f - Daylight;
        Light->SetIntensity(FMath::FInterpTo(Light->Intensity, NightLightIntensities[Index] * Fade, DeltaSeconds, 2));
    }
    if (Fog)
    {
        const float Density = BaseFogDensity * (Weather == TEXT("fog") ? 4.f : Weather == TEXT("rain") ? 1.8f : 1.f);
        Fog->SetFogDensity(FMath::FInterpTo(Fog->FogDensity, Density, DeltaSeconds, 1.5f));
        Fog->SetFogInscatteringColor(FMath::Lerp(FLinearColor(.018f, .027f, .055f),
            FLinearColor(.52f, .60f, .65f) * FMath::Lerp(1.f, .68f, CloudBlend), Daylight));
    }
    if (CloudMaterial)
    {
        // Ordinary cloud cover is not a precipitation cloud type.
        Storminess = FMath::FInterpTo(Storminess, Weather == TEXT("rain") || Weather == TEXT("snow") ? CloudBlend * .9f : 0.f, DeltaSeconds, .4f);
        CloudMaterial->SetScalarParameterValue(TEXT("StormClouds"), Storminess);
        // Rain reshapes the layer toward nimbostratus: lower base, taller and
        // denser deck, near-total coverage, and a darker albedo. Fair-weather
        // cumulus parameters are untouched (Storminess interpolates to 0).
        Cloud->SetLayerBottomAltitude(FMath::Lerp(2.2f, 1.2f, CloudBlend) - Storminess * .45f);
        Cloud->SetLayerHeight(FMath::Lerp(2.5f, 3.5f, CloudBlend) + Storminess * 1.6f);
        // The deck has to stay readable as a deck: the material's
        // (1-coverage) divisor is what draws the shell detail, so a ceiling
        // near 1 clips it to nothing no matter how dense the deck is. .96 was
        // still a flat white sheet; .78 leaves a 22% gap for the towers to
        // silhouette against and gives the divisor room to work.
        CloudMaterial->SetScalarParameterValue(TEXT("Cloud_GlobalCoverage"), FMath::Min(.78f, FMath::Lerp(-.12f, .55f, CloudBlend) + Storminess * .25f));
        CloudMaterial->SetScalarParameterValue(TEXT("Cloud_GlobalDensity"), FMath::Lerp(.012f, .03f, CloudBlend) * (1.f + Storminess * 1.6f));
        // Storm structure, not storm blur. Layout_CloudGlobalScale is pinned at
        // 32 by validate.ps1, so the base lobe is ~8x wider than the window's
        // whole sky patch: everything visible inside one lobe has to come from
        // the mid and high octaves. Prior passes shrank them (.05/.015) and the
        // patch went smooth; Storminess now grows them instead of eating them.
        CloudMaterial->SetVectorParameterValue(TEXT("Noise_Strength"),
            FLinearColor(FMath::Lerp(.8f, .78f, Storminess), FMath::Lerp(.08f, .16f, Storminess),
                FMath::Lerp(.03f, .09f, Storminess), 2.5f));
        CloudMaterial->SetVectorParameterValue(TEXT("Storm_AlbedoColor"),
            FMath::Lerp(FLinearColor(.52f, .55f, .58f, 1.f / 3.f), FLinearColor(.24f, .26f, .30f, 1.f / 3.f), Storminess));
        // Dimmed for a leaden deck, but not so far that the lit crowns stop
        // reading against the shadowed base. .48 flattened the whole mass into
        // one value; the base is carried by extinction (density above), not albedo.
        CloudMaterial->SetVectorParameterValue(TEXT("Cloud_AlbedoColor"),
            FMath::Lerp(FLinearColor(.98f, .98f, .98f, .5f), FLinearColor(.66f, .70f, .76f, .5f), CloudBlend));
        const float Bearing = FMath::DegreesToRadians(Session.WindDirection);
        const float Speed = FMath::Clamp(static_cast<float>(Session.WindSpeed / 3.6), 0.f, 25.f);
        const FVector2D TargetWind(-FMath::Sin(Bearing) * Speed, FMath::Cos(Bearing) * Speed);
        CloudWindMetersPerSecond = FMath::Vector2DInterpTo(CloudWindMetersPerSecond, TargetWind, DeltaSeconds, .5f);
        // Placement is a normalized layout UV, one period is 32 km. Integrating
        // metres/second keeps movement independent of FPS and of the clock slider.
        CloudDriftUV += CloudWindMetersPerSecond * GetWorld()->GetDeltaSeconds() / 32000.f;
        CloudMaterial->SetVectorParameterValue(TEXT("Layout_GlobalTexturePlacement"), FLinearColor(CloudDriftUV.X, CloudDriftUV.Y, 0, 0));
    }
    if (PostProcess)
    {
        const float Speed = Elapsed < FastLightingUntil ? 4.f : .5f;
        PostProcess->Settings.LumenSceneLightingUpdateSpeed = Speed;
        PostProcess->Settings.LumenFinalGatherLightingUpdateSpeed = Speed;
        if (PostProcess->ActorHasTag(TEXT("OOWWindowLookdev")))
        {
            // Share the room-light dusk transition; keep the photographic response stable at night.
            const float Night = Smooth(.58f, .86f, 1.f - Daylight);
            FPostProcessSettings& Settings = PostProcess->Settings;
            Settings.bOverride_BloomIntensity = true;
            Settings.bOverride_BloomSizeScale = true;
            Settings.bOverride_BloomThreshold = true;
            Settings.bOverride_AutoExposureBias = true;
            Settings.BloomIntensity = FMath::Lerp(.675f, FMath::Clamp(NightBloom.GetValueOnGameThread(), 0.f, 4.f), Night);
            Settings.BloomSizeScale = FMath::Lerp(4.f, FMath::Clamp(NightBloomSize.GetValueOnGameThread(), 1.f, 10.f), Night);
            // The volume asset ships threshold -1, so every sky pixel past 1.0
            // fed the bloom. With a bright deck that is a flat white gain on top
            // of the very structure we are trying to show. -1 stays for night.
            Settings.BloomThreshold = FMath::Lerp(1.2f, -1.f, Night);
            // A full overcast deck at noon sits ~1.2 stops above where the
            // towers can still read against it; the day bias is set for that
            // rather than for fair weather.
            Settings.AutoExposureBias = FMath::Lerp(FMath::Lerp(-1.1f, -.5f, CloudBlend), FMath::Clamp(NightExposureBias.GetValueOnGameThread(), -4.f, 2.f), Night);
        }
    }
    if (Sky && !Sky->IsRealTimeCaptureEnabled() && Elapsed - LastSkyCapture > (Elapsed < FastLightingUntil ? 1.f : 30.f))
    {
        Sky->RecaptureSky(); LastSkyCapture = Elapsed;
    }
    if (WindowReflectionCapture && ShouldCaptureWindowReflection(Elapsed, LastWindowReflectionCapture, FastLightingUntil))
    {
        WindowReflectionCapture->CaptureSceneDeferred();
        LastWindowReflectionCapture = Elapsed;
        if (WindowReflectionCaptureRequests == 0)
            for (UMaterialInstanceDynamic* Material : Materials)
            {
                UTexture* Texture = nullptr;
                if (Material->GetTextureParameterValue(FMaterialParameterInfo(TEXT("LocalWindowReflection")), Texture) && Texture == WindowReflectionTexture)
                    Material->SetScalarParameterValue(TEXT("LocalWindowReflectionReady"), 1.f);
            }
        ++WindowReflectionCaptureRequests;
    }
}

void AWindowDirector::UpdateMaterials(float DeltaSeconds)
{
    const bool bRain = ActualWeather() == TEXT("rain");
    const float RainIntensity = !bRain ? 0.f : Session.Weather == TEXT("real")
        ? static_cast<float>(FMath::Clamp(.24 + FMath::Sqrt(Session.Precipitation) * .27, .24, 1.))
        : WindowWeather::PrecipitationIntensityForCode(ActiveWeatherCode());
    if (WindowFrame) WindowFrame->SetRainIntensity(RainIntensity);
    Wetness = FMath::Lerp(Wetness, bRain ? 1.f : 0.f, 1.f - FMath::Exp(-DeltaSeconds * (bRain ? .22f : .012f)));
    Water = FMath::Lerp(Water, bRain ? FMath::Min(1.f, RainIntensity * 1.5f) * Wetness : 0.f, 1.f - FMath::Exp(-DeltaSeconds * (bRain ? .10f : .025f)));
    Session.Wetness = Wetness; Session.Water = Water;
    MaterialTimer += DeltaSeconds;
    if (MaterialTimer < .10f) return;
    MaterialTimer = 0;
    const float Wind = (Session.WindSpeed * .8f + Session.Gust * .2f) / 3.6f;
    for (UMaterialInstanceDynamic* Material : Materials)
    {
        Material->SetScalarParameterValue(TEXT("Wetness"), Wetness);
        Material->SetScalarParameterValue(TEXT("Water"), Water);
        Material->SetScalarParameterValue(TEXT("Night"), 1.f - Daylight);
        Material->SetScalarParameterValue(TEXT("WindStrength"), Wind);
        Material->SetScalarParameterValue(TEXT("RainIntensity"), RainIntensity);
        const float Bearing = FMath::DegreesToRadians(Session.WindDirection);
        Material->SetVectorParameterValue(TEXT("WindDirection"), FLinearColor(-FMath::Sin(Bearing), FMath::Cos(Bearing), 0, 0));
    }
    if (Precipitation)
    {
        const float Bearing = FMath::DegreesToRadians(Session.WindDirection);
        Precipitation->SetWeather(RainIntensity, ActualWeather() == TEXT("snow") ? WindowWeather::PrecipitationIntensityForCode(ActiveWeatherCode()) : 0.f, FVector(-FMath::Sin(Bearing), FMath::Cos(Bearing), 0) * Wind * 100);
    }
}

void AWindowDirector::ToggleAudio()
{
    Session.bAudio = !Session.bAudio;
    UpdateAudio();
}

void AWindowDirector::UpdateAudio()
{
    if (!Session.bAudio) { AmbientAudio->FadeOut(.35f, 0); return; }
    if (!NoiseWave)
    {
        NoiseWave = NewObject<USoundWaveProcedural>(this);
        NoiseWave->SetSampleRate(44100);
        NoiseWave->NumChannels = 1;
        NoiseWave->Duration = INDEFINITELY_LOOPING_DURATION;
        NoiseWave->SoundGroup = SOUNDGROUP_Default;
        AmbientAudio->SetSound(NoiseWave);
        AmbientAudio->SetLowPassFilterEnabled(true);
    }
    AmbientAudio->SetLowPassFilterFrequency(Session.Scene == TEXT("City") || Session.Scene == TEXT("Alley") ? 650 : Session.Scene == TEXT("Coast") ? 420 : 850);
    AmbientAudio->FadeIn(.35f, .032f);
}

void AWindowDirector::OOWAudit()
{
    TSharedRef<FJsonObject> Json = MakeShared<FJsonObject>();
    Json->SetStringField(TEXT("scene"), Session.Scene);
    Json->SetStringField(TEXT("weatherMode"), Session.Weather);
    Json->SetStringField(TEXT("actualWeather"), ActualWeather());
    Json->SetNumberField(TEXT("weatherCode"), ActiveWeatherCode());
    Json->SetStringField(TEXT("weatherLabel"), WindowWeather::LabelForCode(ActiveWeatherCode()));
    Json->SetNumberField(TEXT("reportedCloudCover"), Session.CloudCover);
    Json->SetStringField(TEXT("city"), Session.City);
    Json->SetStringField(TEXT("timezone"), Session.Timezone);
    Json->SetStringField(TEXT("localDateTime"), LocalNow().ToIso8601());
    Json->SetNumberField(TEXT("hour"), Session.Hour);
    Json->SetNumberField(TEXT("utcOffsetSeconds"), Session.OffsetSeconds);
    Json->SetNumberField(TEXT("solarElevation"), SolarElevation);
    Json->SetNumberField(TEXT("quality"), Session.Quality);
    Json->SetNumberField(TEXT("wetness"), Wetness);
    Json->SetNumberField(TEXT("water"), Water);
    Json->SetNumberField(TEXT("materialInstances"), Materials.Num());
    Json->SetNumberField(TEXT("movingCars"), Traffic.Cars.Num());
    Json->SetNumberField(TEXT("trafficLaneChanges"), Traffic.CompletedChanges);
    Json->SetNumberField(TEXT("trafficOvertakeChanges"), Traffic.OvertakeChanges);
    Json->SetNumberField(TEXT("trafficWraps"), Traffic.Wraps);
    Json->SetNumberField(TEXT("trafficMinimumGapMeters"), Traffic.MinimumObservedGap);
    TArray<TSharedPtr<FJsonValue>> TrafficStates;
    for (const FWindowTrafficCar& Car : Traffic.Cars)
    {
        TSharedRef<FJsonObject> State = MakeShared<FJsonObject>();
        State->SetNumberField(TEXT("id"), Car.Id);
        State->SetNumberField(TEXT("lane"), Car.Lane);
        State->SetNumberField(TEXT("targetLane"), Car.TargetLane);
        State->SetNumberField(TEXT("speedKmh"), Car.Speed * 3.6f);
        State->SetNumberField(TEXT("desiredSpeedKmh"), Car.DesiredSpeed * 3.6f);
        const FVector Position = Traffic.Location(Car, 0);
        State->SetNumberField(TEXT("x"), Position.X);
        State->SetNumberField(TEXT("y"), Position.Y);
        State->SetNumberField(TEXT("yaw"), Traffic.Yaw(Car));
        TrafficStates.Add(MakeShared<FJsonValueObject>(State));
    }
    Json->SetArrayField(TEXT("traffic"), TrafficStates);
    Json->SetNumberField(TEXT("capturedFrames"), CapturedFrames);
    Json->SetBoolField(TEXT("desktopFrameReady"), WindowFrame && WindowFrame->IsReady());
    Json->SetNumberField(TEXT("desktopFrameTriangles"), WindowFrame ? WindowFrame->GetTriangleCount() : 0);
    Json->SetNumberField(TEXT("desktopRoomWalls"), WindowFrame ? WindowFrame->GetRoomWallCount() : 0);
    Json->SetNumberField(TEXT("desktopRoomLampLumens"), WindowFrame ? WindowFrame->GetRoomLampLumens() : 0);
    Json->SetStringField(TEXT("desktopFrameStyle"), WindowFrame ? WindowFrame->GetStyle().ToString() : TEXT("none"));
    Json->SetNumberField(TEXT("windowRainIntensity"), WindowFrame ? WindowFrame->GetRainIntensity() : 0);
    Json->SetBoolField(TEXT("interfaceHidden"), VisibilityControl && VisibilityControl->IsInterfaceHidden());
    Json->SetNumberField(TEXT("sunLux"), Sun ? Sun->Intensity : 0);
    Json->SetNumberField(TEXT("nightLights"), NightLights.Num());
    Json->SetNumberField(TEXT("activeHeadlights"), Traffic.ActiveHeadlights);
    Json->SetNumberField(TEXT("maxHeadlights"), FWindowTraffic::MaxHeadlights);
    if (IConsoleVariable* Lumens = IConsoleManager::Get().FindConsoleVariable(TEXT("oow.HeadlightLumens")))
        Json->SetNumberField(TEXT("headlightLumens"), Lumens->GetFloat());
    int32 InteriorLights = 0;
    float InteriorLumens = 0;
    for (ULightComponent* Light : NightLights)
        if (Light->GetOwner()->ActorHasTag(TEXT("OOWInteriorLight"))) { ++InteriorLights; InteriorLumens += Light->Intensity; }
    Json->SetNumberField(TEXT("interiorLights"), InteriorLights);
    Json->SetNumberField(TEXT("interiorLightLumens"), InteriorLumens);
    if (GEngine && GEngine->GameViewport && GEngine->GameViewport->Viewport)
    {
        if (ULocalPlayer* Player = GetWorld()->GetFirstLocalPlayerFromController())
        {
            FSceneViewFamilyContext Family(FSceneViewFamily::ConstructionValues(GEngine->GameViewport->Viewport, GetWorld()->Scene, GEngine->GameViewport->EngineShowFlags).SetRealtimeUpdate(true));
            FVector Location;
            FRotator Rotation;
            if (FSceneView* View = Player->CalcSceneView(&Family, Location, Rotation, GEngine->GameViewport->Viewport))
            {
                const FFinalPostProcessSettings& Settings = View->FinalPostProcessSettings;
                TSharedRef<FJsonObject> Exposure = MakeShared<FJsonObject>();
                Exposure->SetNumberField(TEXT("bloomIntensity"), Settings.BloomIntensity);
                Exposure->SetNumberField(TEXT("bloomSizeScale"), Settings.BloomSizeScale);
                Exposure->SetNumberField(TEXT("bloomThreshold"), Settings.BloomThreshold);
                Exposure->SetNumberField(TEXT("exposureBias"), Settings.AutoExposureBias);
                Exposure->SetNumberField(TEXT("minBrightness"), Settings.AutoExposureMinBrightness);
                Exposure->SetNumberField(TEXT("maxBrightness"), Settings.AutoExposureMaxBrightness);
                Exposure->SetNumberField(TEXT("lastEyeAdaptationExposure"), View->GetLastEyeAdaptationExposure());
                Exposure->SetNumberField(TEXT("lastAverageSceneLuminance"), View->GetLastAverageSceneLuminance());
                Json->SetObjectField(TEXT("finalViewPostProcess"), Exposure);
            }
        }
    }
    Json->SetNumberField(TEXT("giUpdateSpeed"), PostProcess ? PostProcess->Settings.LumenSceneLightingUpdateSpeed : 0);
    Json->SetBoolField(TEXT("liveTime"), Session.bLiveTime);
    Json->SetBoolField(TEXT("fallbackWeather"), Session.bFallback);
    Json->SetBoolField(TEXT("fetchingWeather"), bFetching);
    Json->SetBoolField(TEXT("audio"), Session.bAudio);
    Json->SetBoolField(TEXT("cameraBound"), bCameraBound);
    Json->SetBoolField(TEXT("precipitationActor"), IsValid(Precipitation));
    Json->SetBoolField(TEXT("birdActor"), IsValid(Birds));
    Json->SetBoolField(TEXT("birdGeometryReady"), Birds && Birds->IsReady());
    Json->SetNumberField(TEXT("activeBirds"), Birds ? Birds->GetActiveCount() : 0);
    Json->SetNumberField(TEXT("completedBirdFlights"), Birds ? Birds->GetCompletedFlights() : 0);
    Json->SetBoolField(TEXT("testMode"), bTestMode);
    Json->SetStringField(TEXT("capture"), CapturePath);
    Json->SetBoolField(TEXT("captureSaved"), !CapturePath.IsEmpty() && IFileManager::Get().FileSize(*CapturePath) > 0);
    Json->SetNumberField(TEXT("skyIntensity"), Sky ? Sky->Intensity : 0);
    Json->SetNumberField(TEXT("windowReflectionCaptureRequests"), WindowReflectionCaptureRequests);
    Json->SetNumberField(TEXT("windowReflectionResolution"), WindowReflectionTexture ? WindowReflectionTexture->SizeX : 0);
    Json->SetNumberField(TEXT("windowReflectionLastCaptureSeconds"), LastWindowReflectionCapture);
    if (bTestMode && bCaptureRequested && WindowReflectionTexture && FParse::Param(FCommandLine::Get(), TEXT("OOWExportWindowReflection")))
    {
        TUniquePtr<FArchive> File(IFileManager::Get().CreateFileWriter(*FPaths::ChangeExtension(CapturePath, TEXT("reflection.hdr"))));
        Json->SetBoolField(TEXT("windowReflectionExported"), File && FImageUtils::ExportRenderTargetCubeAsHDR(WindowReflectionTexture, *File));
    }
    if (WindowReflectionCapture)
    {
        const FVector Position = WindowReflectionCapture->GetComponentLocation();
        Json->SetArrayField(TEXT("windowReflectionLocation"), { MakeShared<FJsonValueNumber>(Position.X), MakeShared<FJsonValueNumber>(Position.Y), MakeShared<FJsonValueNumber>(Position.Z) });
        Json->SetBoolField(TEXT("windowReflectionHDR"), WindowReflectionCapture->CaptureSource == SCS_SceneColorHDRNoAlpha);
        Json->SetBoolField(TEXT("windowReflectionAutoMips"), WindowReflectionTexture && WindowReflectionTexture->bAutoGenerateMips);
        Json->SetBoolField(TEXT("windowReflectionHidesFrame"), !WindowFrame || WindowReflectionCapture->HiddenActors.Contains(WindowFrame.Get()));
        int32 BoundMaterials = 0;
        for (UMaterialInstanceDynamic* Material : Materials)
        {
            UTexture* Texture = nullptr;
            if (Material->GetTextureParameterValue(FMaterialParameterInfo(TEXT("LocalWindowReflection")), Texture) && Texture == WindowReflectionTexture)
                ++BoundMaterials;
        }
        Json->SetNumberField(TEXT("windowReflectionBoundMaterials"), BoundMaterials);
    }
    Json->SetNumberField(TEXT("fogDensity"), Fog ? Fog->FogDensity : 0);
    Json->SetNumberField(TEXT("baseFogDensity"), BaseFogDensity);
    Json->SetNumberField(TEXT("cloudiness"), Cloudiness);
    Json->SetNumberField(TEXT("cloudLayerBottomKm"), Cloud ? Cloud->LayerBottomAltitude : 0);
    Json->SetNumberField(TEXT("cloudLayerHeightKm"), Cloud ? Cloud->LayerHeight : 0);
    Json->SetNumberField(TEXT("cloudViewSampleScale"), Cloud ? Cloud->ViewSampleCountScale : 0);
    Json->SetNumberField(TEXT("visibleSkyFraction"), VisibleSkyFraction);
    Json->SetNumberField(TEXT("visibleSkyPixels"), VisibleSkyPixels);
    Json->SetNumberField(TEXT("cloudTargetSampleScale"), CloudTargetSampleScale);
    if (SkySampling)
    {
        // Which pixels the sky measurement actually covered. Without this a sky
        // brightness number cannot be told apart from a roofline one.
        TArray<uint8> Mask;
        FIntPoint MaskSize;
        bool bOnly = true;
        SkySampling->CopySkyMask(Mask, MaskSize, bOnly);
        Json->SetNumberField(TEXT("skyMaskWidth"), MaskSize.X);
        Json->SetNumberField(TEXT("skyMaskHeight"), MaskSize.Y);
        Json->SetBoolField(TEXT("skyMaskIsOnlySky"), bOnly);
        if (MaskSize.X > 0) Json->SetStringField(TEXT("skyMask"), BytesToHexLower(Mask.GetData(), Mask.Num()));
    }
    Json->SetBoolField(TEXT("cloudShadowsEnabled"), Sun && Sun->bCastCloudShadows);
    Json->SetNumberField(TEXT("cloudAnimationSeconds"), GetWorld()->GetTimeSeconds());
    Json->SetArrayField(TEXT("cloudDriftUV"), { MakeShared<FJsonValueNumber>(CloudDriftUV.X), MakeShared<FJsonValueNumber>(CloudDriftUV.Y) });
    Json->SetNumberField(TEXT("atmosphereMieScale"), Atmosphere ? Atmosphere->MieScatteringScale : 0);
    Json->SetNumberField(TEXT("atmosphereBaseMieScale"), BaseMieScattering);
    for (const TCHAR* Name : { TEXT("r.VolumetricCloud"), TEXT("r.VolumetricRenderTarget"), TEXT("r.VolumetricRenderTarget.Mode"), TEXT("r.VolumetricCloud.DistanceToSampleMaxCount") })
        if (IConsoleVariable* Variable = IConsoleManager::Get().FindConsoleVariable(Name)) Json->SetNumberField(Name, Variable->GetFloat());
    Json->SetNumberField(TEXT("sunAzimuthRadians"), SunAzimuth);
    Json->SetBoolField(TEXT("sunSweep"), bSunSweep);
    if (CloudMaterial)
    {
        TSharedRef<FJsonObject> CloudParameters = MakeShared<FJsonObject>();
        for (const TCHAR* Name : { TEXT("Cloud_GlobalCoverage"), TEXT("Cloud_GlobalDensity"), TEXT("StormClouds"), TEXT("Layout_CloudGlobalScale") })
        {
            float Value;
            if (CloudMaterial->GetScalarParameterValue(FMaterialParameterInfo(Name), Value)) CloudParameters->SetNumberField(Name, Value);
        }
        FLinearColor WindControls;
        if (CloudMaterial->GetVectorParameterValue(FMaterialParameterInfo(TEXT("Layout_WindControls")), WindControls))
            CloudParameters->SetArrayField(TEXT("Layout_WindControls"), { MakeShared<FJsonValueNumber>(WindControls.R), MakeShared<FJsonValueNumber>(WindControls.G), MakeShared<FJsonValueNumber>(WindControls.B), MakeShared<FJsonValueNumber>(WindControls.A) });
        Json->SetObjectField(TEXT("cloudParameters"), CloudParameters);
    }
    int32 ActorCount = 0, MeshCount = 0, NaniteCount = 0, WetMaterialCount = 0, GlassFronts = 0, GlassBackings = 0;
    int32 WindMeshes = 0, EvaluatedWindMeshes = 0, WindMaterialSlots = 0, AnchoredWindMeshes = 0, CompiledWindSlots = 0;
    float WindStrength = 0;
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        ++ActorCount;
        if (It->ActorHasTag(TEXT("OOWWindowGlassFront"))) ++GlassFronts;
        if (It->ActorHasTag(TEXT("OOWWindowGlassBacking"))) ++GlassBackings;
        TInlineComponentArray<UStaticMeshComponent*> Meshes;
        It->GetComponents(Meshes);
        for (UStaticMeshComponent* Mesh : Meshes)
        {
            if (!Mesh->GetStaticMesh()) continue;
            ++MeshCount;
            if (Mesh->GetStaticMesh()->HasValidNaniteData()) ++NaniteCount;
            if (It->ActorHasTag(TEXT("OOWWind")))
            {
                ++WindMeshes;
                if (Mesh->bEvaluateWorldPositionOffset) ++EvaluatedWindMeshes;
                const TArray<float>& Bounds = Mesh->GetCustomPrimitiveData().Data;
                if (Bounds.Num() >= 2 && Bounds[1] > 0) ++AnchoredWindMeshes;
                for (int32 Index = 0; Index < Mesh->GetNumMaterials(); ++Index)
                {
                    float Value = 0;
                    UMaterialInterface* Material = Mesh->GetMaterial(Index);
                    if (Material && Material->GetScalarParameterValue(FMaterialParameterInfo(TEXT("WindStrength")), Value))
                    {
                        ++WindMaterialSlots;
                        if (Material->IsUsingWorldPositionOffset_Concurrent(GMaxRHIShaderPlatform)) ++CompiledWindSlots;
                        WindStrength = FMath::Max(WindStrength, Value);
                    }
                }
            }
        }
    }
    for (UMaterialInstanceDynamic* Material : Materials)
    {
        float Value;
        if (Material->GetScalarParameterValue(FMaterialParameterInfo(TEXT("Wetness")), Value)) ++WetMaterialCount;
    }
    Json->SetNumberField(TEXT("actors"), ActorCount);
    Json->SetNumberField(TEXT("windowGlassFronts"), GlassFronts);
    Json->SetNumberField(TEXT("windowGlassBackings"), GlassBackings);
    Json->SetNumberField(TEXT("staticMeshComponents"), MeshCount);
    Json->SetNumberField(TEXT("naniteMeshComponents"), NaniteCount);
    Json->SetNumberField(TEXT("wetnessMaterials"), WetMaterialCount);
    Json->SetNumberField(TEXT("windMeshComponents"), WindMeshes);
    Json->SetNumberField(TEXT("evaluatedWindMeshComponents"), EvaluatedWindMeshes);
    Json->SetNumberField(TEXT("windMaterialSlots"), WindMaterialSlots);
    Json->SetNumberField(TEXT("anchoredWindMeshComponents"), AnchoredWindMeshes);
    Json->SetNumberField(TEXT("compiledWindMaterialSlots"), CompiledWindSlots);
    Json->SetNumberField(TEXT("windStrengthMetersPerSecond"), WindStrength);
    for (const TCHAR* Name : { TEXT("r.DynamicGlobalIlluminationMethod"), TEXT("r.ReflectionMethod"), TEXT("r.Lumen.DiffuseIndirect.Allow"), TEXT("r.Lumen.ScreenProbeGather.TwoSidedFoliageBackfaceDiffuse"), TEXT("r.Lumen.Reflections.Allow"), TEXT("r.Lumen.TranslucencyReflections.FrontLayer.Enable"), TEXT("r.Lumen.TranslucencyReflections.FrontLayer.Allow"), TEXT("r.Lumen.HardwareRayTracing.LightingMode"), TEXT("r.Lumen.HardwareRayTracing"), TEXT("r.RayTracing"), TEXT("r.AntiAliasingMethod"), TEXT("sg.GlobalIlluminationQuality"), TEXT("sg.ReflectionQuality"), TEXT("r.ScreenPercentage") })
        if (IConsoleVariable* Variable = IConsoleManager::Get().FindConsoleVariable(Name)) Json->SetNumberField(Name, Variable->GetFloat());
    if (FrameTimes.Num())
    {
        TArray<float> Sorted = FrameTimes;
        Sorted.Sort();
        double Total = 0;
        for (float Time : FrameTimes) Total += Time;
        Json->SetNumberField(TEXT("frameTimeSamples"), FrameTimes.Num());
        Json->SetNumberField(TEXT("frameTimeMeanMs"), Total / FrameTimes.Num());
        Json->SetNumberField(TEXT("frameTimeP95Ms"), Sorted[FMath::Min(Sorted.Num() - 1, FMath::FloorToInt(Sorted.Num() * .95f))]);
    }
    if (Camera)
    {
        const FVector P = Camera->GetActorLocation();
        Json->SetArrayField(TEXT("camera"), { MakeShared<FJsonValueNumber>(P.X), MakeShared<FJsonValueNumber>(P.Y), MakeShared<FJsonValueNumber>(P.Z) });
        Json->SetNumberField(TEXT("fov"), Camera->GetCameraComponent()->FieldOfView);
    }
    TArray<TSharedPtr<FJsonValue>> Missing;
    for (const FString& Tag : MissingTags) Missing.Add(MakeShared<FJsonValueString>(Tag));
    Json->SetArrayField(TEXT("missingTags"), Missing);
    FString Text;
    FJsonSerializer::Serialize(Json, TJsonWriterFactory<>::Create(&Text));
    const FString Path = CapturePath.IsEmpty() ? FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("oow-state.json")) : FPaths::ChangeExtension(CapturePath, TEXT("json"));
    IFileManager::Get().MakeDirectory(*FPaths::ProjectSavedDir(), true);
    const bool bSaved = FFileHelper::SaveStringToFile(Text, *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    UE_LOG(LogTemp, Display, TEXT("OOW_AUDIT %s %s"), bSaved ? TEXT("saved") : TEXT("failed"), *Path);
}

void AWindowDirector::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    Session.bCollapsed = bCollapsed;
    Session.bPrivacyDismissed = bPrivacyDismissed;
    if (GeoRequest) { GeoRequest->OnProcessRequestComplete().Unbind(); GeoRequest->CancelRequest(); }
    if (ForecastRequest) { ForecastRequest->OnProcessRequestComplete().Unbind(); ForecastRequest->CancelRequest(); }
    for (IConsoleObject* Command : Commands) if (Command) IConsoleManager::Get().UnregisterConsoleObject(Command, false);
    Commands.Empty();
    if (Interface && GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(Interface.ToSharedRef());
    Interface.Reset();
    VisibilityControl.Reset();
    SkySampling.Reset();
    FScreenshotRequest::OnScreenshotRequestProcessed().Remove(ScreenshotHandle);
    if (Desktop) { Desktop->Shutdown(); Desktop.Reset(); }
    AmbientAudio->Stop();
    Super::EndPlay(EndPlayReason);
}

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowReflectionCadenceTest, "OutOfWindow.WindowReflection.CaptureCadence",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FWindowReflectionCadenceTest::RunTest(const FString& Parameters)
{
    TestFalse(TEXT("Wait for initial lighting"), ShouldCaptureWindowReflection(2.f, -100.f, 4.f));
    TestTrue(TEXT("First capture after lighting starts"), ShouldCaptureWindowReflection(2.1f, -100.f, 4.f));
    TestFalse(TEXT("Warmup does not capture every frame"), ShouldCaptureWindowReflection(3.f, 2.1f, 4.f));
    TestTrue(TEXT("Capture the settled weather after the fast GI period"), ShouldCaptureWindowReflection(106.f, 103.f, 104.f));
    TestTrue(TEXT("Warm up the Lumen cache every two seconds"), ShouldCaptureWindowReflection(6.1f, 4.1f, 4.f));
    TestFalse(TEXT("Stable lighting waits thirty seconds"), ShouldCaptureWindowReflection(37.f, 8.1f, 4.f));
    TestTrue(TEXT("Periodic refresh follows current lighting"), ShouldCaptureWindowReflection(38.2f, 8.1f, 4.f));
    TestTrue(TEXT("User lighting changes refresh promptly"), ShouldCaptureWindowReflection(42.f, 40.f, 44.f));
    TestFalse(TEXT("Fast changes still respect rate limit"), ShouldCaptureWindowReflection(41.f, 40.f, 44.f));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowLocationTest, "OutOfWindow.Location.OptionalTracking",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FWindowLocationTest::RunTest(const FString& Parameters)
{
    TestFalse(TEXT("IP tracking is opt-in"), FWindowSession().bFollowIP);
    TestTrue(TEXT("Boundary coordinates"), ValidLocation(-90, 180, -12));
    TestTrue(TEXT("Zero coordinates"), ValidLocation(0, 0, 14));
    TestFalse(TEXT("Invalid latitude"), ValidLocation(91, 0, 8));
    TestFalse(TEXT("Invalid longitude"), ValidLocation(0, -181, 8));
    TestFalse(TEXT("Invalid offset"), ValidLocation(0, 0, 15));
    TestFalse(TEXT("NaN"), ValidLocation(std::numeric_limits<double>::quiet_NaN(), 0, 8));
    TestFalse(TEXT("Infinity"), ValidLocation(0, std::numeric_limits<double>::infinity(), 8));
    UWorld* World = UWorld::CreateWorld(EWorldType::Game, false);
    AWindowDirector* Director = World->SpawnActor<AWindowDirector>();
    if (!TestNotNull(TEXT("Test director"), Director)) { World->DestroyWorld(false); return false; }
    const FWindowSession SavedSession = Session;
    const FString SavedIni = GGameUserSettingsIni;
    GGameUserSettingsIni = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("LocationAutomation.ini"));
    GConfig->Add(GGameUserSettingsIni, FConfigFile());
    Session = FWindowSession();
    Director->bTestMode = true;
    Director->ApplyLocation(false, 1.29, 103.85, TEXT("Singapore"), 8);
    bool FollowIP = true;
    double Latitude = 0;
    GConfig->GetBool(TEXT("OutOfWindow.Location"), TEXT("FollowIP"), FollowIP, GGameUserSettingsIni);
    GConfig->GetDouble(TEXT("OutOfWindow.Location"), TEXT("Latitude"), Latitude, GGameUserSettingsIni);
    TestFalse(TEXT("Manual mode persisted"), FollowIP);
    TestEqual(TEXT("Coordinate persisted"), Latitude, 1.29);
    FConfigFile DiskSettings;
    DiskSettings.Read(GGameUserSettingsIni);
    double DiskLatitude = 0;
    DiskSettings.GetDouble(TEXT("OutOfWindow.Location"), TEXT("Latitude"), DiskLatitude);
    TestEqual(TEXT("Coordinate saved to disk for restart"), DiskLatitude, 1.29);
    Director->ApplyLocation(false, 91, 0, TEXT("Invalid"), 8);
    TestEqual(TEXT("Invalid setting leaves selection intact"), Session.ManualLatitude, 1.29);
    Director->bTestMode = false;
    Director->RefreshWeather();
    TestFalse(TEXT("Manual refresh never creates an IP request"), Director->GeoRequest.IsValid());
    TestTrue(TEXT("Forecast uses selected coordinates"), Director->ForecastRequest.IsValid()
        && Director->ForecastRequest->GetURL().Contains(TEXT("latitude=1.290000&longitude=103.850000")));
    if (Director->ForecastRequest)
    {
        Director->ForecastRequest->OnProcessRequestComplete().Unbind();
        Director->ForecastRequest->CancelRequest();
    }
    AddExpectedError(TEXT("OutOfWindow uses offline example weather"), EAutomationExpectedErrorFlags::Contains, 1);
    Director->UseOfflineWeather();
    TestEqual(TEXT("Offline preserves city"), Session.City, FString(TEXT("Singapore")));
    TestEqual(TEXT("Offline preserves coordinates"), Session.Latitude, 1.29);
    TestTrue(TEXT("Offline weather is flagged"), Session.bFallback);
    Director->bTestMode = true;
    Director->ApplyLocation(true, 1.29, 103.85, TEXT("Singapore"), 8);
    GConfig->GetBool(TEXT("OutOfWindow.Location"), TEXT("FollowIP"), FollowIP, GGameUserSettingsIni);
    TestTrue(TEXT("IP opt-in persisted"), FollowIP);
    Director->ApplyLocation(false, 1.29, 103.85, TEXT("Singapore"), 8);
    TestFalse(TEXT("Tracking can be disabled again"), Session.bFollowIP);
    GConfig->UnloadFile(GGameUserSettingsIni);
    IFileManager::Get().Delete(*GGameUserSettingsIni);
    GGameUserSettingsIni = SavedIni;
    World->DestroyWorld(false);
    Session = SavedSession;
    return true;
}
#endif
