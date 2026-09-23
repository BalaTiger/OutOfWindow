#include "WindowDirector.h"
#include "WindowDesktop.h"
#include "WindowPrecipitation.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/AudioComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/MeshComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/VolumetricCloudComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "GameFramework/GameUserSettings.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/CommandLine.h"
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
#include "Widgets/Input/SSlider.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

namespace
{
struct FWindowSession
{
    FString Scene = TEXT("Alley"), Weather = TEXT("real"), City = TEXT("上海"), Timezone = TEXT("Asia/Shanghai");
    double Latitude = 31.23, Longitude = 121.47, OffsetSeconds = 28800;
    double Temperature = 22, CloudCover = 35, Precipitation = 0, WindSpeed = 8, WindDirection = 240, Gust = 8;
    int32 WeatherCode = 1, Quality = 1;
    float Hour = 10, Wetness = 0, Water = 0;
    bool bLiveTime = true, bAudio = false, bHasWeather = false, bFallback = true, bTest = false;
    bool bRefreshPending = false;
    bool bCompact = false, bCollapsed = false, bPrivacyDismissed = false;
};
FWindowSession Session;

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

FString WeatherForCode(int32 Code)
{
    if (Code == 45 || Code == 48) return TEXT("fog");
    if (Code == 71 || Code == 73 || Code == 75 || Code == 77 || Code == 85 || Code == 86) return TEXT("snow");
    if ((Code >= 51 && Code <= 67) || (Code >= 80 && Code <= 82) || Code >= 95) return TEXT("rain");
    return TEXT("clear");
}

FString WeatherLabel(const FString& Mode)
{
    if (Mode == TEXT("rain")) return TEXT("雨");
    if (Mode == TEXT("snow")) return TEXT("雪");
    if (Mode == TEXT("fog")) return TEXT("雾");
    return Session.WeatherCode == 3 && Session.Weather == TEXT("real") ? TEXT("阴天") : TEXT("晴");
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
    if (bTestMode)
    {
        UseOfflineWeather();
        Session.bLiveTime = false;
        Session.bAudio = false;
        Session.Wetness = Session.Water = 0;
        FParse::Value(FCommandLine::Get(), TEXT("OOWTestSeconds="), TestSeconds);
        TestSeconds = FMath::Clamp(TestSeconds, 1.f, 300.f);
    }
    Session.Scene = UGameplayStatics::GetCurrentLevelName(this, true);
    bCompact = Session.bCompact;
    bCollapsed = Session.bCollapsed;
    bPrivacyDismissed = Session.bPrivacyDismissed;
    Wetness = Session.Wetness;
    Water = Session.Water;
    FindSceneActors();
    BindCamera();
    RegisterCommands();
    if (!bTestMode || FParse::Param(FCommandLine::Get(), TEXT("OOWTestDesktop"))) { Desktop = MakeUnique<FWindowDesktop>(); Desktop->Initialize(this); }
    MakeInterface();
    OOWQuality(Session.Quality);

    float StartHour;
    int32 StartQuality;
    FString StartWeather;
    if (FParse::Value(FCommandLine::Get(), TEXT("OOWTime="), StartHour)) OOWTime(StartHour);
    if (FParse::Value(FCommandLine::Get(), TEXT("OOWWeather="), StartWeather)) OOWWeather(StartWeather);
    if (FParse::Value(FCommandLine::Get(), TEXT("OOWTestHour="), StartHour)) OOWTime(StartHour);
    if (FParse::Value(FCommandLine::Get(), TEXT("OOWTestWeather="), StartWeather)) OOWWeather(StartWeather);
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
    if (bTestMode)
    {
        TestStartedAt = GetWorld()->GetTimeSeconds();
        IFileManager::Get().MakeDirectory(*FPaths::GetPath(CapturePath), true);
        ScreenshotHandle = FScreenshotRequest::OnScreenshotRequestProcessed().AddWeakLambda(this, [this]
        {
            if (bCaptureRequested) { OOWAudit(); ExitFrames = 6; }
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
            CarParts.Add({ Actor, Actor->GetActorLocation(), Car });
            CarStartY.FindOrAdd(Car, Actor->GetActorLocation().Y);
        }
        if (Actor->ActorHasTag(TEXT("OOWCamera"))) Camera = Cast<ACameraActor>(Actor);
        if (Actor->ActorHasTag(TEXT("OOWSun"))) Sun = Actor->FindComponentByClass<UDirectionalLightComponent>();
        if (Actor->ActorHasTag(TEXT("OOWNightLight")))
        {
            if (UPointLightComponent* Light = Actor->FindComponentByClass<UPointLightComponent>())
            {
                NightLights.Add(Light);
                NightLightIntensities.Add(Light->Intensity);
            }
        }
        if (Actor->ActorHasTag(TEXT("OOWSky"))) Sky = Actor->FindComponentByClass<USkyLightComponent>();
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
    if (!Fog) MissingTags.Add(TEXT("OOWFog"));
    if (!Cloud) MissingTags.Add(TEXT("OOWCloud"));
    if (!PostProcess) MissingTags.Add(TEXT("OOWPostProcess"));
    if (Fog) BaseFogDensity = Fog->FogDensity;
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
    if (Sun) { Sun->SetMobility(EComponentMobility::Movable); Sun->SetAtmosphereSunLight(true); }
    if (Sky) { Sky->SetMobility(EComponentMobility::Movable); Sky->SetRealTimeCapture(true); }
    if (Cloud && Cloud->Material.LoadSynchronous())
    {
        CloudMaterial = UMaterialInstanceDynamic::Create(Cloud->Material.Get(), this);
        Cloud->SetMaterial(CloudMaterial);
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
    Register(TEXT("OOWAudit"), [this](const TArray<FString>&) { OOWAudit(); });
}

void AWindowDirector::MakeInterface()
{
    if (!GEngine || !GEngine->GameViewport) return;
    const FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), 13);
    auto Button = [Font](TAttribute<FText> Label, TFunction<void()> Action)
    {
        return SNew(SButton).ContentPadding(FMargin(5, 5)).OnClicked_Lambda([Action = MoveTemp(Action)] { Action(); return FReply::Handled(); })
            [SNew(STextBlock).Text(Label).Font(Font).ColorAndOpacity(FLinearColor(.88f, .90f, .85f))];
    };
    auto Label = [](const TCHAR* Text) { return TAttribute<FText>(FText::FromString(Text)); };
    TSharedRef<SHorizontalBox> SceneButtons = SNew(SHorizontalBox);
    const TCHAR* SceneKeys[] = { TEXT("City"), TEXT("Alley"), TEXT("Village"), TEXT("Forest"), TEXT("Coast") };
    const TCHAR* SceneNames[] = { TEXT("都市"), TEXT("后巷"), TEXT("村庄"), TEXT("山林"), TEXT("海滨") };
    for (int32 Index = 0; Index < 5; ++Index)
    {
        const FString Key = SceneKeys[Index], Name = SceneNames[Index];
        SceneButtons->AddSlot().FillWidth(1).Padding(2)[Button(TAttribute<FText>::CreateLambda([Key, Name] { return FText::FromString((Session.Scene == Key ? TEXT("● ") : TEXT("")) + Name); }), [this, Key] { OOWScene(Key); })];
    }
    TSharedRef<SHorizontalBox> WeatherButtons = SNew(SHorizontalBox);
    const TCHAR* WeatherKeys[] = { TEXT("real"), TEXT("clear"), TEXT("rain"), TEXT("snow"), TEXT("fog") };
    const TCHAR* WeatherNames[] = { TEXT("实时"), TEXT("晴"), TEXT("雨"), TEXT("雪"), TEXT("雾") };
    for (int32 Index = 0; Index < 5; ++Index)
    {
        const FString Key = WeatherKeys[Index], Name = WeatherNames[Index];
        WeatherButtons->AddSlot().FillWidth(1).Padding(2)[Button(TAttribute<FText>::CreateLambda([Key, Name] { return FText::FromString((Session.Weather == Key ? TEXT("● ") : TEXT("")) + Name); }), [this, Key] { OOWWeather(Key); })];
    }
    TSharedRef<SHorizontalBox> QualityButtons = SNew(SHorizontalBox);
    const TCHAR* QualityNames[] = { TEXT("节能"), TEXT("均衡"), TEXT("精细") };
    for (int32 Index = 0; Index < 3; ++Index)
    {
        const FString Name = QualityNames[Index];
        QualityButtons->AddSlot().FillWidth(1).Padding(2)[Button(TAttribute<FText>::CreateLambda([Index, Name] { return FText::FromString((Session.Quality == Index ? TEXT("● ") : TEXT("")) + Name); }), [this, Index] { OOWQuality(Index); })];
    }
    Interface = SNew(SOverlay)
        + SOverlay::Slot().VAlign(VAlign_Top).Padding(15)
        [SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush(TEXT("WhiteBrush"))).BorderBackgroundColor(FLinearColor(.02f, .03f, .03f, .85f)).Padding(10)
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)[SNew(STextBlock).Text(FText::FromString(TEXT("OUT OF WINDOW  ·  一扇会呼吸的窗"))).Font(Font)]
                + SHorizontalBox::Slot().AutoWidth()[Button(Label(TEXT("穿透")), [this] { DesktopButton(TEXT("ClickThrough")); })]
                + SHorizontalBox::Slot().AutoWidth()[Button(Label(TEXT("收起")), [this] { DesktopButton(TEXT("Compact")); })]
                + SHorizontalBox::Slot().AutoWidth()[Button(Label(TEXT("—")), [this] { DesktopButton(TEXT("Minimize")); })]
                + SHorizontalBox::Slot().AutoWidth()[Button(Label(TEXT("□")), [this] { DesktopButton(TEXT("Maximize")); })]
                + SHorizontalBox::Slot().AutoWidth()[Button(Label(TEXT("×")), [this] { DesktopButton(TEXT("Close")); })]]]
        + SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Top).Padding(30, 86, 20, 20)
        [SNew(SVerticalBox).Visibility_Lambda([this] { return bCompact ? EVisibility::Collapsed : EVisibility::SelfHitTestInvisible; })
            + SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).Text_Lambda([this] { return StatusText(); }).Font(Font).ShadowOffset(FVector2D(1, 1))]
            + SVerticalBox::Slot().AutoHeight().Padding(0, 12)[Button(Label(TEXT("刷新天气")), [this] { RefreshWeather(); })]]
        + SOverlay::Slot().HAlign(HAlign_Right).VAlign(VAlign_Bottom).Padding(20, 20, 28, 35)
        [SNew(SBox).WidthOverride(430).Visibility_Lambda([this] { return bCompact ? EVisibility::Collapsed : EVisibility::SelfHitTestInvisible; })
            [SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush(TEXT("WhiteBrush"))).BorderBackgroundColor(FLinearColor(.02f, .035f, .04f, .90f)).Padding(14)
                [SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight()[Button(TAttribute<FText>::CreateLambda([this] { return FText::FromString(bCollapsed ? TEXT("此刻的窗外 · 展开") : TEXT("此刻的窗外 · 收起")); }), [this] { bCollapsed = !bCollapsed; })]
                    + SVerticalBox::Slot().AutoHeight()
                    [SNew(SVerticalBox).Visibility_Lambda([this] { return bCollapsed ? EVisibility::Collapsed : EVisibility::SelfHitTestInvisible; })
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 10)[SNew(STextBlock).Text_Lambda([this] { return ClockText(); }).Font(FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), 24))]
                        + SVerticalBox::Slot().AutoHeight()[Button(TAttribute<FText>::CreateLambda([] { return FText::FromString(Session.bLiveTime ? TEXT("● 跟随当地") : TEXT("跟随当地")); }), [this] { Session.bLiveTime = !Session.bLiveTime; FastLightingUntil = GetWorld()->GetTimeSeconds() + 4; })]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 12)[SNew(SSlider).Value_Lambda([] { return Session.Hour / (23.f + 59.f / 60.f); }).OnValueChanged_Lambda([this](float Value) { OOWTime(FMath::RoundToFloat(Value * 1439.f) / 60.f); })]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 4)[WeatherButtons]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 4)[QualityButtons]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 4)[SceneButtons]
                        + SVerticalBox::Slot().AutoHeight().Padding(0, 5)[Button(TAttribute<FText>::CreateLambda([] { return FText::FromString(Session.bAudio ? TEXT("● 环境声景") : TEXT("环境声景")); }), [this] { ToggleAudio(); })]]]]]
        + SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Center).Padding(30)
        [SNew(SBox).WidthOverride(300).Visibility_Lambda([this] { return bCompact ? EVisibility::Collapsed : EVisibility::HitTestInvisible; })
            [SNew(STextBlock).Text_Lambda([]
            {
                const FString Text = Session.Scene == TEXT("City") ? TEXT("01 / 05  都市\n街区与天际线") : Session.Scene == TEXT("Alley") ? TEXT("02 / 05  后巷\n雨篷与石板路") : Session.Scene == TEXT("Village") ? TEXT("03 / 05  村庄\n田野与屋瓦") : Session.Scene == TEXT("Forest") ? TEXT("04 / 05  山林\n松涛与溪流") : TEXT("05 / 05  海滨\n潮汐与暮光");
                return FText::FromString(Text);
            }).Font(FCoreStyle::GetDefaultFontStyle(TEXT("Regular"), 22)).ShadowOffset(FVector2D(1, 2))]]
        + SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Bottom).Padding(30, 20, 20, 28)
        [SNew(SVerticalBox).Visibility_Lambda([this] { return bCompact ? EVisibility::Collapsed : EVisibility::SelfHitTestInvisible; })
            + SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).Text_Lambda([] { return FText::FromString(FString::Printf(TEXT("固定窗景 · 实时天气 · Lumen · %.0f FPS"), 1. / FMath::Max(.001, FApp::GetDeltaTime()))); }).Font(Font)]
            + SVerticalBox::Slot().AutoHeight().Padding(0, 8)[SNew(SBox).Visibility_Lambda([this] { return bPrivacyDismissed ? EVisibility::Collapsed : EVisibility::Visible; })
                [Button(Label(TEXT("城市级 IP 近似定位 · 不保存地址   ×")), [this] { bPrivacyDismissed = true; })]]];
    GEngine->GameViewport->AddViewportWidgetContent(Interface.ToSharedRef(), 10);
}

FText AWindowDirector::StatusText() const
{
    const FDateTime Now = LocalNow();
    const TCHAR* Status = bFetching ? TEXT("正在同步本地天空") : Session.bFallback ? TEXT("离线演示数据") : TEXT("实时天空 · 已更新");
    return FText::FromString(FString::Printf(TEXT("%s\n%s  %.0f°C\n%s · 风 %.0f km/h · %02d:%02d"), Status, *Session.City, Session.Temperature, *WeatherLabel(ActualWeather()), Session.WindSpeed, Now.GetHour(), Now.GetMinute()));
}

FText AWindowDirector::ClockText() const
{
    const int32 Minutes = FMath::RoundToInt(Session.Hour * 60) % 1440;
    const TCHAR* Period = SolarElevation < -6 ? (Session.Hour < 5 ? TEXT("深夜") : TEXT("夜晚")) : SolarElevation < 6 ? (SolarMinutes < 720 ? TEXT("晨曦") : TEXT("暮色")) : SolarElevation < 12 ? (SolarMinutes < 720 ? TEXT("清晨") : TEXT("黄昏")) : Session.Hour < 11 ? TEXT("上午") : Session.Hour < 14 ? TEXT("日中") : TEXT("午后");
    return FText::FromString(FString::Printf(TEXT("%02d:%02d  %s"), Minutes / 60, Minutes % 60, Period));
}

void AWindowDirector::DesktopButton(FName Action)
{
    if (Action == TEXT("Compact")) bCompact = !bCompact;
    if (DesktopAction) DesktopAction(Action);
}

void AWindowDirector::SetCompactMode(bool bEnabled)
{
    bCompact = Session.bCompact = bEnabled;
}

FString AWindowDirector::ActualWeather() const { return Session.Weather == TEXT("real") ? WeatherForCode(Session.WeatherCode) : Session.Weather; }

void AWindowDirector::OOWTime(float Hour)
{
    if (!FMath::IsFinite(Hour)) return;
    const float NewHour = FMath::Fmod(FMath::Fmod(Hour, 24.f) + 24.f, 24.f);
    if (FMath::Abs(NewHour - Session.Hour) > .12f) FastLightingUntil = GetWorld()->GetTimeSeconds() + 3;
    Session.Hour = NewHour;
    Session.bLiveTime = false;
}

void AWindowDirector::OOWWeather(const FString& Mode)
{
    FString Normalized = Mode.ToLower();
    if (Normalized == TEXT("live")) Normalized = TEXT("real");
    if (Normalized != TEXT("real") && Normalized != TEXT("clear") && Normalized != TEXT("rain") && Normalized != TEXT("snow") && Normalized != TEXT("fog")) return;
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
    SetCVar(TEXT("r.Lumen.Reflections.Allow"), 1);
    SetCVar(TEXT("r.Lumen.TranslucencyReflections.FrontLayer.Enable"), Session.Quality > 0 ? 1 : 0);
    SetCVar(TEXT("r.Lumen.TranslucencyReflections.FrontLayer.Allow"), Session.Quality > 0 ? 1 : 0);
    SetCVar(TEXT("r.Lumen.HardwareRayTracing.LightingMode"), Session.Quality == 2 ? 2 : 0);
    SetCVar(TEXT("r.SkyLight.RealTimeReflectionCapture.TimeSlice"), 1);
}

void AWindowDirector::RefreshWeather()
{
    if (bFetching || bTestMode) return;
    bFetching = true;
    Session.bRefreshPending = true;
    GeoRequest = FHttpModule::Get().CreateRequest();
    GeoRequest->SetURL(TEXT("https://ipwho.is/?fields=success,city,region,country,latitude,longitude,timezone"));
    GeoRequest->SetVerb(TEXT("GET"));
    GeoRequest->SetTimeout(8);
    GeoRequest->OnProcessRequestComplete().BindWeakLambda(this, [this](FHttpRequestPtr, FHttpResponsePtr Response, bool bSuccess)
    {
        TSharedPtr<FJsonObject> Json;
        bool bGeoOK = false;
        if (!ReadJson(Response, bSuccess, Json) || !Json->TryGetBoolField(TEXT("success"), bGeoOK) || !bGeoOK) { UseOfflineWeather(); return; }
        const double Latitude = Number(Json, TEXT("latitude"), 31.23);
        const double Longitude = Number(Json, TEXT("longitude"), 121.47);
        if (FMath::Abs(Latitude) > 90 || FMath::Abs(Longitude) > 180) { UseOfflineWeather(); return; }
        FString City = Session.City, Timezone = Session.Timezone;
        Json->TryGetStringField(TEXT("city"), City);
        const TSharedPtr<FJsonObject>* Zone = nullptr;
        if (Json->TryGetObjectField(TEXT("timezone"), Zone)) (*Zone)->TryGetStringField(TEXT("id"), Timezone);
        FetchForecast(Latitude, Longitude, City, Timezone);
    });
    if (!GeoRequest->ProcessRequest()) UseOfflineWeather();
}

void AWindowDirector::FetchForecast(double Latitude, double Longitude, const FString& City, const FString& Timezone)
{
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
        Session.OffsetSeconds = Number(Json, TEXT("utc_offset_seconds"), 28800);
        Json->TryGetStringField(TEXT("timezone"), Session.Timezone);
        Session.Temperature = Number(*Current, TEXT("temperature_2m"), 22);
        Session.WeatherCode = static_cast<int32>(Number(*Current, TEXT("weather_code"), 1));
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
    Session.City = TEXT("上海"); Session.Timezone = TEXT("Asia/Shanghai");
    Session.Latitude = 31.23; Session.Longitude = 121.47; Session.OffsetSeconds = 28800;
    Session.Temperature = 22; Session.CloudCover = 35; Session.WeatherCode = 1; Session.Precipitation = 0;
    Session.WindSpeed = 8; Session.Gust = 8; Session.WindDirection = 240;
    Session.bHasWeather = true; Session.bFallback = true; Session.bRefreshPending = false; bFetching = false;
    UE_LOG(LogTemp, Warning, TEXT("OutOfWindow uses offline Shanghai weather"));
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
    UpdateMaterials(DeltaSeconds);
    for (const FCarPart& Part : CarParts)
    {
        if (!Part.Actor.IsValid()) continue;
        const float StartY = CarStartY[Part.Car];
        const float Speed = .015f + FMath::Frac(Part.Car * .618034f) * .012f;
        float Phase = FMath::Fmod((1600.f - StartY) / 21400.f + GetWorld()->GetTimeSeconds() * Speed * (Part.Car % 2 ? -1.f : 1.f), 1.f);
        if (Phase < 0) Phase += 1;
        Part.Actor->SetActorLocation(Part.Origin + FVector(0, 1600.f - Phase * 21400.f - StartY, 0));
    }
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
        }
        const float Elapsed = Now - TestStartedAt;
        if (!bShadersCompiling && Elapsed > 2) FrameTimes.Add(DeltaSeconds * 1000.f);
        if (!bCaptureRequested && !bShadersCompiling && Elapsed >= TestSeconds)
        {
            bCaptureRequested = true;
            OOWAudit();
            FScreenshotRequest::RequestScreenshot(CapturePath, FParse::Param(FCommandLine::Get(), TEXT("OOWCaptureUI")), false);
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
    const float Cloudiness = Session.Weather == TEXT("real") ? Session.CloudCover / 100.f : Weather == TEXT("clear") ? .12f : Weather == TEXT("fog") ? .88f : .78f;
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
        const float TargetLux = 90000.f * Smooth(-.015f, .08f, FMath::Sin(Elevation)) * (1 - Cloudiness * .93f);
        Sun->SetIntensity(FMath::FInterpTo(Sun->Intensity, TargetLux, DeltaSeconds, 2));
        Sun->SetLightColor(FMath::Lerp(FLinearColor(1.f, .94f, .86f), FLinearColor(1.f, .53f, .26f), Glow * .8f));
    }
    if (Sky) Sky->SetIntensity(FMath::FInterpTo(Sky->Intensity, .07f + Daylight * .93f, DeltaSeconds, 2));
    for (int32 Index = 0; Index < NightLights.Num(); ++Index)
        NightLights[Index]->SetIntensity(FMath::FInterpTo(NightLights[Index]->Intensity, NightLightIntensities[Index] * (1.f - Daylight), DeltaSeconds, 2));
    if (Fog)
    {
        const float Density = BaseFogDensity * (Weather == TEXT("fog") ? 4.f : Weather == TEXT("rain") ? 1.8f : 1.f);
        Fog->SetFogDensity(FMath::FInterpTo(Fog->FogDensity, Density, DeltaSeconds, 1.5f));
        Fog->SetFogInscatteringColor(FMath::Lerp(FLinearColor(.018f, .027f, .055f), FLinearColor(.52f, .60f, .65f), Daylight));
    }
    if (CloudMaterial)
    {
        const float CloudBlend = Smooth(.12f, .78f, Cloudiness);
        CloudMaterial->SetScalarParameterValue(TEXT("Cloud_GlobalCoverage"), FMath::Lerp(-.4f, .25f, CloudBlend));
        CloudMaterial->SetScalarParameterValue(TEXT("Cloud_GlobalDensity"), FMath::Lerp(.006f, .016f, CloudBlend));
    }
    if (PostProcess)
    {
        const float Speed = Elapsed < FastLightingUntil ? 4.f : .5f;
        PostProcess->Settings.LumenSceneLightingUpdateSpeed = Speed;
        PostProcess->Settings.LumenFinalGatherLightingUpdateSpeed = Speed;
    }
    if (Sky && !Sky->IsRealTimeCaptureEnabled() && Elapsed - LastSkyCapture > (Elapsed < FastLightingUntil ? 1.f : 30.f))
    {
        Sky->RecaptureSky(); LastSkyCapture = Elapsed;
    }
}

void AWindowDirector::UpdateMaterials(float DeltaSeconds)
{
    const bool bRain = ActualWeather() == TEXT("rain");
    const float RainIntensity = bRain ? static_cast<float>(FMath::Clamp(.24 + FMath::Sqrt(Session.Weather == TEXT("real") ? Session.Precipitation : 2.5) * .27, .24, 1.)) : 0.f;
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
        Precipitation->SetWeather(RainIntensity, ActualWeather() == TEXT("snow") ? .7f : 0.f, FVector(-FMath::Sin(Bearing), FMath::Cos(Bearing), 0) * Wind * 100);
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
    Json->SetNumberField(TEXT("movingCars"), CarStartY.Num());
    Json->SetNumberField(TEXT("sunLux"), Sun ? Sun->Intensity : 0);
    Json->SetNumberField(TEXT("nightLights"), NightLights.Num());
    Json->SetNumberField(TEXT("giUpdateSpeed"), PostProcess ? PostProcess->Settings.LumenSceneLightingUpdateSpeed : 0);
    Json->SetBoolField(TEXT("liveTime"), Session.bLiveTime);
    Json->SetBoolField(TEXT("fallbackWeather"), Session.bFallback);
    Json->SetBoolField(TEXT("fetchingWeather"), bFetching);
    Json->SetBoolField(TEXT("audio"), Session.bAudio);
    Json->SetBoolField(TEXT("cameraBound"), bCameraBound);
    Json->SetBoolField(TEXT("precipitationActor"), IsValid(Precipitation));
    Json->SetBoolField(TEXT("testMode"), bTestMode);
    Json->SetStringField(TEXT("capture"), CapturePath);
    Json->SetBoolField(TEXT("captureSaved"), !CapturePath.IsEmpty() && IFileManager::Get().FileSize(*CapturePath) > 0);
    Json->SetNumberField(TEXT("skyIntensity"), Sky ? Sky->Intensity : 0);
    Json->SetNumberField(TEXT("fogDensity"), Fog ? Fog->FogDensity : 0);
    Json->SetNumberField(TEXT("baseFogDensity"), BaseFogDensity);
    Json->SetNumberField(TEXT("sunAzimuthRadians"), SunAzimuth);
    Json->SetBoolField(TEXT("sunSweep"), bSunSweep);
    if (CloudMaterial)
    {
        TSharedRef<FJsonObject> CloudParameters = MakeShared<FJsonObject>();
        for (const TCHAR* Name : { TEXT("Cloud_GlobalCoverage"), TEXT("Cloud_GlobalDensity"), TEXT("StormClouds") })
        {
            float Value;
            if (CloudMaterial->GetScalarParameterValue(FMaterialParameterInfo(Name), Value)) CloudParameters->SetNumberField(Name, Value);
        }
        FLinearColor WindControls;
        if (CloudMaterial->GetVectorParameterValue(FMaterialParameterInfo(TEXT("Layout_WindControls")), WindControls))
            CloudParameters->SetArrayField(TEXT("Layout_WindControls"), { MakeShared<FJsonValueNumber>(WindControls.R), MakeShared<FJsonValueNumber>(WindControls.G), MakeShared<FJsonValueNumber>(WindControls.B), MakeShared<FJsonValueNumber>(WindControls.A) });
        Json->SetObjectField(TEXT("cloudParameters"), CloudParameters);
    }
    int32 ActorCount = 0, MeshCount = 0, NaniteCount = 0, WetMaterialCount = 0;
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        ++ActorCount;
        TInlineComponentArray<UStaticMeshComponent*> Meshes;
        It->GetComponents(Meshes);
        for (UStaticMeshComponent* Mesh : Meshes)
        {
            if (!Mesh->GetStaticMesh()) continue;
            ++MeshCount;
            if (Mesh->GetStaticMesh()->HasValidNaniteData()) ++NaniteCount;
        }
    }
    for (UMaterialInstanceDynamic* Material : Materials)
    {
        float Value;
        if (Material->GetScalarParameterValue(FMaterialParameterInfo(TEXT("Wetness")), Value)) ++WetMaterialCount;
    }
    Json->SetNumberField(TEXT("actors"), ActorCount);
    Json->SetNumberField(TEXT("staticMeshComponents"), MeshCount);
    Json->SetNumberField(TEXT("naniteMeshComponents"), NaniteCount);
    Json->SetNumberField(TEXT("wetnessMaterials"), WetMaterialCount);
    for (const TCHAR* Name : { TEXT("r.DynamicGlobalIlluminationMethod"), TEXT("r.ReflectionMethod"), TEXT("r.Lumen.DiffuseIndirect.Allow"), TEXT("r.Lumen.Reflections.Allow"), TEXT("r.Lumen.TranslucencyReflections.FrontLayer.Enable"), TEXT("r.Lumen.TranslucencyReflections.FrontLayer.Allow"), TEXT("r.Lumen.HardwareRayTracing.LightingMode"), TEXT("r.Lumen.HardwareRayTracing"), TEXT("r.RayTracing"), TEXT("r.AntiAliasingMethod"), TEXT("sg.GlobalIlluminationQuality"), TEXT("sg.ReflectionQuality"), TEXT("r.ScreenPercentage") })
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
    Session.bCompact = bCompact;
    Session.bCollapsed = bCollapsed;
    Session.bPrivacyDismissed = bPrivacyDismissed;
    if (GeoRequest) { GeoRequest->OnProcessRequestComplete().Unbind(); GeoRequest->CancelRequest(); }
    if (ForecastRequest) { ForecastRequest->OnProcessRequestComplete().Unbind(); ForecastRequest->CancelRequest(); }
    for (IConsoleObject* Command : Commands) if (Command) IConsoleManager::Get().UnregisterConsoleObject(Command, false);
    Commands.Empty();
    if (Interface && GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(Interface.ToSharedRef());
    Interface.Reset();
    FScreenshotRequest::OnScreenshotRequestProcessed().Remove(ScreenshotHandle);
    if (Desktop) { Desktop->Shutdown(); Desktop.Reset(); }
    AmbientAudio->Stop();
    Super::EndPlay(EndPlayReason);
}
