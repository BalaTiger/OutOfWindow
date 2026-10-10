#include "WindowSkySampling.h"
#include "BufferVisualizationData.h"
#include "ImagePixelData.h"
#include "ImageWriteStream.h"
#include "Materials/Material.h"
#include "Engine/Texture.h"
#include "Curves/CurveFloat.h"
#include "SceneManagement.h"
#include "UnrealClient.h"
#include "HAL/IConsoleManager.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

#include "FXRenderingUtils.h"
#include "HAL/PlatformTime.h"
#include "Misc/ScopeLock.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "RHIGPUReadback.h"
#include "ScreenPass.h"
#include "SceneInterface.h"
#include "VolumetricCloudRendering.h"
#include "VolumetricCloudProxy.h"
#include "MaterialShared.h"
#include "Materials/MaterialRenderProxy.h"

namespace
{
const FIntPoint SampleSize(128, 72);
}

float WindowSkyFraction(const float* Depth, FIntPoint Size, int32 RowPitch)
{
    if (!Depth || Size.X <= 0 || Size.Y <= 0 || RowPitch < Size.X) return -1;
    int32 SkyPixels = 0;
    for (int32 Y = 0; Y < Size.Y; ++Y)
        for (int32 X = 0; X < Size.X; ++X)
            SkyPixels += Depth[Y * RowPitch + X] == 0.f;
    return static_cast<float>(SkyPixels) / (Size.X * Size.Y);
}

bool WindowSkyMask(const float* Depth, FIntPoint Size, int32 RowPitch, TArray<uint8>& OutMask, bool& OutOnly)
{
    if (!Depth || Size.X <= 0 || Size.Y <= 0 || RowPitch < Size.X) return false;
    OutMask.SetNumUninitialized(Size.X * Size.Y);
    OutOnly = true;
    for (int32 Y = 0; Y < Size.Y; ++Y)
        for (int32 X = 0; X < Size.X; ++X)
        {
            const bool bSky = Depth[Y * RowPitch + X] == 0.f;
            OutMask[Y * Size.X + X] = bSky ? 255 : 0;
            OutOnly &= bSky;
        }
    return true;
}

float WindowCloudSampleScale(float VisibleSkyPixels, int32 Quality, float BudgetPixels)
{
    Quality = FMath::Clamp(Quality, 0, 2);
    const float Minimum = .5f * (Quality + 1), Maximum = Quality + 1.f;
    if (!FMath::IsFinite(VisibleSkyPixels) || VisibleSkyPixels <= 0) return Minimum;
    BudgetPixels = FMath::IsFinite(BudgetPixels) ? FMath::Clamp(BudgetPixels, 20000.f, 1000000.f) : 200000.f;
    // Pixel-times-samples is a workload estimate, not a GPU time guarantee; profile before raising these caps.
    return FMath::Clamp(BudgetPixels * Minimum / VisibleSkyPixels, Minimum, Maximum);
}

FWindowSkySampling::FWindowSkySampling(const FAutoRegister& AutoRegister, UWorld* World)
    : FWorldSceneViewExtension(AutoRegister, World)
{
}

FWindowSkySampling::~FWindowSkySampling() = default;

// Float32 side pipes on the actual primary game view. They never replace the main output.
void FWindowSkySampling::SetupView(FSceneViewFamily& Family, FSceneView& View)
{
    FString TestCapture;
    if (!FParse::Value(FCommandLine::Get(), TEXT("OOWCapture="), TestCapture)
        || !FParse::Param(FCommandLine::Get(), TEXT("OOWDiagHDR"))
        || !FScreenshotRequest::IsScreenshotRequested() || !View.bIsGameView
        || View.bIsSceneCapture || View.bIsReflectionCapture || View.bIsPlanarReflection
        || (!Family.Views.IsEmpty() && Family.Views[0] != &View)) return;
    const FString Stem = FPaths::ChangeExtension(FScreenshotRequest::GetFilename(), TEXT(""));
    const double WorldSeconds = Family.Time.GetWorldTimeSeconds();
    const uint32 Frame = Family.FrameNumber;
    auto& PP = View.FinalPostProcessSettings;
    PP.BufferVisualizationOverviewMaterials.Reset();
    TSharedRef<FJsonObject> Applied=MakeShared<FJsonObject>();
    Applied->SetNumberField(TEXT("worldSecondsAtSetup"),WorldSeconds);
    Applied->SetNumberField(TEXT("frameAtSetup"),Frame);
    Applied->SetNumberField(TEXT("FilmSlope"),PP.FilmSlope);
    Applied->SetNumberField(TEXT("FilmToe"),PP.FilmToe);
    Applied->SetNumberField(TEXT("FilmShoulder"),PP.FilmShoulder);
    Applied->SetNumberField(TEXT("FilmBlackClip"),PP.FilmBlackClip);
    Applied->SetNumberField(TEXT("FilmWhiteClip"),PP.FilmWhiteClip);
    Applied->SetNumberField(TEXT("BlueCorrection"),PP.BlueCorrection);
    Applied->SetNumberField(TEXT("ExpandGamut"),PP.ExpandGamut);
    Applied->SetNumberField(TEXT("ToneCurveAmount"),PP.ToneCurveAmount);
    Applied->SetNumberField(TEXT("WhiteTemp"),PP.WhiteTemp);
    Applied->SetNumberField(TEXT("WhiteTint"),PP.WhiteTint);
    Applied->SetNumberField(TEXT("ColorCorrectionShadowsMax"),PP.ColorCorrectionShadowsMax);
    Applied->SetNumberField(TEXT("ColorCorrectionHighlightsMin"),PP.ColorCorrectionHighlightsMin);
    Applied->SetNumberField(TEXT("ColorCorrectionHighlightsMax"),PP.ColorCorrectionHighlightsMax);
    Applied->SetNumberField(TEXT("VignetteIntensity"),PP.VignetteIntensity);
    Applied->SetNumberField(TEXT("FilmGrainIntensity"),PP.FilmGrainIntensity);
    Applied->SetNumberField(TEXT("BloomIntensity"),PP.BloomIntensity);
    Applied->SetNumberField(TEXT("BloomThreshold"),PP.BloomThreshold);
    Applied->SetNumberField(TEXT("BloomSizeScale"),PP.BloomSizeScale);
    Applied->SetNumberField(TEXT("LensFlareIntensity"),PP.LensFlareIntensity);
    Applied->SetNumberField(TEXT("LensFlareThreshold"),PP.LensFlareThreshold);
    Applied->SetNumberField(TEXT("ColorGradingIntensity"),PP.ColorGradingIntensity);
    Applied->SetNumberField(TEXT("LocalExposureHighlightContrastScale"),PP.LocalExposureHighlightContrastScale);
    Applied->SetNumberField(TEXT("LocalExposureShadowContrastScale"),PP.LocalExposureShadowContrastScale);
    Applied->SetNumberField(TEXT("LocalExposureHighlightThreshold"),PP.LocalExposureHighlightThreshold);
    Applied->SetNumberField(TEXT("LocalExposureShadowThreshold"),PP.LocalExposureShadowThreshold);
    Applied->SetNumberField(TEXT("LocalExposureDetailStrength"),PP.LocalExposureDetailStrength);
    Applied->SetNumberField(TEXT("LocalExposureBlurredLuminanceBlend"),PP.LocalExposureBlurredLuminanceBlend);
    Applied->SetNumberField(TEXT("LocalExposureHighlightThresholdStrength"),PP.LocalExposureHighlightThresholdStrength);
    Applied->SetNumberField(TEXT("LocalExposureShadowThresholdStrength"),PP.LocalExposureShadowThresholdStrength);
    Applied->SetNumberField(TEXT("LocalExposureMethod"),static_cast<int32>(PP.LocalExposureMethod));
    Applied->SetArrayField(TEXT("SceneColorTint"),{MakeShared<FJsonValueNumber>(PP.SceneColorTint.R),MakeShared<FJsonValueNumber>(PP.SceneColorTint.G),MakeShared<FJsonValueNumber>(PP.SceneColorTint.B),MakeShared<FJsonValueNumber>(PP.SceneColorTint.A)});
    auto SaveVector=[&Applied](const TCHAR* Name,const FVector4& V){Applied->SetArrayField(Name,{MakeShared<FJsonValueNumber>(V.X),MakeShared<FJsonValueNumber>(V.Y),MakeShared<FJsonValueNumber>(V.Z),MakeShared<FJsonValueNumber>(V.W)});};
    SaveVector(TEXT("ColorSaturation"),PP.ColorSaturation);
    SaveVector(TEXT("ColorContrast"),PP.ColorContrast);
    SaveVector(TEXT("ColorGamma"),PP.ColorGamma);
    SaveVector(TEXT("ColorGain"),PP.ColorGain);
    SaveVector(TEXT("ColorOffset"),PP.ColorOffset);
    SaveVector(TEXT("ColorSaturationShadows"),PP.ColorSaturationShadows);
    SaveVector(TEXT("ColorContrastShadows"),PP.ColorContrastShadows);
    SaveVector(TEXT("ColorGammaShadows"),PP.ColorGammaShadows);
    SaveVector(TEXT("ColorGainShadows"),PP.ColorGainShadows);
    SaveVector(TEXT("ColorOffsetShadows"),PP.ColorOffsetShadows);
    SaveVector(TEXT("ColorSaturationMidtones"),PP.ColorSaturationMidtones);
    SaveVector(TEXT("ColorContrastMidtones"),PP.ColorContrastMidtones);
    SaveVector(TEXT("ColorGammaMidtones"),PP.ColorGammaMidtones);
    SaveVector(TEXT("ColorGainMidtones"),PP.ColorGainMidtones);
    SaveVector(TEXT("ColorOffsetMidtones"),PP.ColorOffsetMidtones);
    SaveVector(TEXT("ColorSaturationHighlights"),PP.ColorSaturationHighlights);
    SaveVector(TEXT("ColorContrastHighlights"),PP.ColorContrastHighlights);
    SaveVector(TEXT("ColorGammaHighlights"),PP.ColorGammaHighlights);
    SaveVector(TEXT("ColorGainHighlights"),PP.ColorGainHighlights);
    SaveVector(TEXT("ColorOffsetHighlights"),PP.ColorOffsetHighlights);
    TArray<TSharedPtr<FJsonValue>> LUTs;
    for(const auto& Entry:PP.ContributingLUTs)
    {
        TSharedRef<FJsonObject> L=MakeShared<FJsonObject>();
        L->SetNumberField(TEXT("weight"),Entry.Weight);
        L->SetStringField(TEXT("texture"),Entry.LUTTexture?Entry.LUTTexture->GetPathName():TEXT("null-neutral"));
        LUTs.Add(MakeShared<FJsonValueObject>(L));
    }
    Applied->SetArrayField(TEXT("contributingLUTs"),LUTs);
    Applied->SetStringField(TEXT("LocalExposureHighlightContrastCurve"),PP.LocalExposureHighlightContrastCurve?PP.LocalExposureHighlightContrastCurve->GetPathName():TEXT("null"));
    Applied->SetStringField(TEXT("LocalExposureShadowContrastCurve"),PP.LocalExposureShadowContrastCurve?PP.LocalExposureShadowContrastCurve->GetPathName():TEXT("null"));
    FString AppliedText;FJsonSerializer::Serialize(Applied,TJsonWriterFactory<>::Create(&AppliedText));
    FFileHelper::SaveStringToFile(AppliedText,*(Stem+TEXT(".hdr-pp.json")));

    TArray<FName> Keys;
    for (const TCHAR* Stage : { TEXT("PreTonemapHDRColor"), TEXT("PostTonemapHDRColor") })
    {
        UMaterialInterface* Material = GetBufferVisualizationData().GetMaterial(FName(Stage));
        if (!Material) { UE_LOG(LogTemp, Error, TEXT("OOW HDR missing stage material %s"), Stage); continue; }
        const FString StageName(Stage);
        const int32 BlendLocation = static_cast<int32>(Material->GetMaterial()->BlendableLocation);
        const bool bDisablePreExposure = Material->GetMaterial()->bDisablePreExposureScale;
        auto Pipe = MakeShared<FImagePixelPipe, ESPMode::ThreadSafe>();
        Pipe->bIsExpecting32BitPixelData = true;
        Pipe->AddEndpoint([Stem, StageName, WorldSeconds, Frame, BlendLocation, bDisablePreExposure](TUniquePtr<FImagePixelData>&& Pixels)
        {
            const void* Data = nullptr; int64 ByteCount = 0;
            if (!Pixels || Pixels->GetType() != EImagePixelType::Float32 || Pixels->GetNumChannels() != 4 || !Pixels->GetRawData(Data, ByteCount))
            { UE_LOG(LogTemp, Error, TEXT("OOW HDR expected valid Float32 RGBA stage %s"), *StageName); return; }
            const FIntPoint Size = Pixels->GetSize();
            const FString StageStem = Stem + TEXT(".") + StageName;
            TSharedRef<FJsonObject> Meta = MakeShared<FJsonObject>();
            Meta->SetNumberField(TEXT("width"), Size.X); Meta->SetNumberField(TEXT("height"), Size.Y);
            Meta->SetNumberField(TEXT("bitDepth"), Pixels->GetBitDepth()); Meta->SetNumberField(TEXT("sourceBufferBytes"), ByteCount);
            Meta->SetNumberField(TEXT("worldSecondsAtSetup"), WorldSeconds); Meta->SetNumberField(TEXT("frameAtSetup"), Frame);
            Meta->SetNumberField(TEXT("materialBlendableLocation"), BlendLocation);
            Meta->SetBoolField(TEXT("materialDisablePreExposureScale"), bDisablePreExposure);
            Meta->SetStringField(TEXT("stage"), StageName);
            Meta->SetStringField(TEXT("storage"), TEXT("unchanged RGBA float32 pixel bytes, row-major; no gamma or normalization"));
            Meta->SetStringField(TEXT("semantics"), StageName.StartsWith(TEXT("Pre")) ? TEXT("Pre-tonemap buffer; source pre-exposure recorded separately in same-frame hdr-view.json") : TEXT("Post-tonemap/device output; float32 side pipe does not recover prior source precision"));
            TArray<TSharedPtr<FJsonValue>> Regions;
            struct FRegion { const TCHAR* Name; FIntRect Box; };
            const FRegion Boxes[] = {
                { TEXT("sky"), FIntRect(128,125,420,485) },
                { TEXT("asphalt"), FIntRect(1178,1250,1203,1275) },
                { TEXT("stone_horizontal"), FIntRect(2170,422,2320,434) },
                { TEXT("stone_vertical"), FIntRect(1810,580,1835,710) },
                { TEXT("visible_glass"), FIntRect(2130,630,2205,690) }
            };
            for (const FRegion& Region : Boxes)
            {
                const FIntRect Box(FMath::FloorToInt(Region.Box.Min.X * Size.X / 2560.0), FMath::FloorToInt(Region.Box.Min.Y * Size.Y / 1440.0),
                    FMath::FloorToInt(Region.Box.Max.X * Size.X / 2560.0), FMath::FloorToInt(Region.Box.Max.Y * Size.Y / 1440.0));
                TArray<uint8> Bytes; Bytes.SetNumUninitialized(Box.Width()*Box.Height()*sizeof(FLinearColor));
                for (int32 Y=0; Y<Box.Height(); ++Y)
                    FMemory::Memcpy(Bytes.GetData()+Y*Box.Width()*sizeof(FLinearColor), static_cast<const uint8*>(Data)+((Y+Box.Min.Y)*Size.X+Box.Min.X)*sizeof(FLinearColor), Box.Width()*sizeof(FLinearColor));
                const FString File = StageStem + TEXT(".") + Region.Name + TEXT(".rgba-f32.bin");
                const bool bSaved = FFileHelper::SaveArrayToFile(Bytes,*File);
                TSharedRef<FJsonObject> R = MakeShared<FJsonObject>(); R->SetStringField(TEXT("name"),Region.Name); R->SetStringField(TEXT("file"),File);
                R->SetArrayField(TEXT("box"),{ MakeShared<FJsonValueNumber>(Box.Min.X), MakeShared<FJsonValueNumber>(Box.Min.Y), MakeShared<FJsonValueNumber>(Box.Max.X), MakeShared<FJsonValueNumber>(Box.Max.Y) });
                R->SetNumberField(TEXT("bytes"),Bytes.Num()); R->SetBoolField(TEXT("saved"),bSaved); Regions.Add(MakeShared<FJsonValueObject>(R));
            }
            Meta->SetArrayField(TEXT("regions"),Regions);
            FString Text; FJsonSerializer::Serialize(Meta,TJsonWriterFactory<>::Create(&Text));
            FFileHelper::SaveStringToFile(Text,*(StageStem+TEXT(".json")));
            UE_LOG(LogTemp,Display,TEXT("OOW_HDR_STAGE %s %dx%d Float32 same-frame world=%.9f"),*StageName,Size.X,Size.Y,WorldSeconds);
        });
        PP.BufferVisualizationOverviewMaterials.Add(Material);
        PP.BufferVisualizationPipes.Add(Material->GetFName(),Pipe);
        Keys.Add(Material->GetFName());
    }
    FScopeLock Lock(&MeasurementLock);
    DiagnosticHDRStem=Stem; DiagnosticHDRWorldSeconds=WorldSeconds; DiagnosticHDRFrame=Frame;
    DiagnosticHDRKeys=MoveTemp(Keys);
}

void FWindowSkySampling::PrePostProcessPass_RenderThread(FRDGBuilder& GraphBuilder, const FSceneView& View, const FPostProcessingInputs& Inputs)
{
    if (!View.bIsGameView || View.bIsSceneCapture || View.bIsReflectionCapture || View.bIsPlanarReflection
        || !View.Family || View.Family->Views.IsEmpty() || View.Family->Views[0] != &View) return;
    FString Stem; double Seconds=0; uint32 Frame=0;
    { FScopeLock Lock(&MeasurementLock); if(DiagnosticHDRStem.IsEmpty() || DiagnosticHDRKeys.Num()!=2) return;
      for (const FName Key : DiagnosticHDRKeys) if (!View.FinalPostProcessSettings.BufferVisualizationPipes.Contains(Key)) return;
      if (FMath::Abs(View.Family->Time.GetWorldTimeSeconds()-DiagnosticHDRWorldSeconds)>0.00001) return;
      Stem=MoveTemp(DiagnosticHDRStem); Seconds=DiagnosticHDRWorldSeconds; Frame=DiagnosticHDRFrame; }
    // Snapshot Renderer-produced parameters for this exact primary frame.
    // These are RT uniform inputs, not GPU executed sample counters. The unchanged
    // side pipes below separately read actual GPU HDR/SDR pixel bytes.
    TSharedRef<FJsonObject> CloudAudit=MakeShared<FJsonObject>();
    CloudAudit->SetNumberField(TEXT("worldSeconds"),View.Family->Time.GetWorldTimeSeconds());
    CloudAudit->SetNumberField(TEXT("frame"),View.Family->FrameNumber);
    CloudAudit->SetStringField(TEXT("auditLocation"),TEXT("PrePostProcess primary render thread, after cloud passes queued; before RDG GPU execution"));
    CloudAudit->SetStringField(TEXT("semantics"),TEXT("Actual Renderer-created cloud uniform inputs and scene proxy; not GPU executed sample counts"));
    const FIntRect ActualViewRect=UE::FXRenderingUtils::GetRawViewRectUnsafe(View);
    CloudAudit->SetArrayField(TEXT("scaledViewRect"),{MakeShared<FJsonValueNumber>(ActualViewRect.Min.X),MakeShared<FJsonValueNumber>(ActualViewRect.Min.Y),MakeShared<FJsonValueNumber>(ActualViewRect.Max.X),MakeShared<FJsonValueNumber>(ActualViewRect.Max.Y)});
    const FVolumetricCloudRenderSceneInfo* CloudInfo=View.Family->Scene?View.Family->Scene->GetVolumetricCloudSceneInfo():nullptr;
    CloudAudit->SetBoolField(TEXT("cloudSceneInfoPresent"),CloudInfo!=nullptr);
    if(CloudInfo)
    {
        const auto& C=CloudInfo->GetVolumetricCloudCommonShaderParameters();
        const auto& Proxy=CloudInfo->GetVolumetricCloudSceneProxy();
        CloudAudit->SetBoolField(TEXT("rendererCommonUniformBufferValid"),CloudInfo->GetVolumetricCloudCommonShaderParametersUB().IsValid());
        TSharedRef<FJsonObject> Common=MakeShared<FJsonObject>();
        Common->SetNumberField(TEXT("SampleCountClamp"),C.SampleCountClamp);
        Common->SetNumberField(TEXT("SampleCountMin"),C.SampleCountMin);
        Common->SetNumberField(TEXT("SampleCountMax"),C.SampleCountMax);
        Common->SetNumberField(TEXT("ShadowSampleCountMax"),C.ShadowSampleCountMax);
        Common->SetNumberField(TEXT("ShadowTracingMaxDistance"),C.ShadowTracingMaxDistance);
        Common->SetNumberField(TEXT("InvDistanceToSampleCountMax"),C.InvDistanceToSampleCountMax);
        Common->SetNumberField(TEXT("PlanetRadiusKm"),C.PlanetRadiusKm);
        Common->SetNumberField(TEXT("BottomRadiusKm"),C.BottomRadiusKm);
        Common->SetNumberField(TEXT("TopRadiusKm"),C.TopRadiusKm);
        Common->SetNumberField(TEXT("StopTracingTransmittanceThreshold"),C.StopTracingTransmittanceThreshold);
        Common->SetNumberField(TEXT("SkyLightCloudBottomVisibility"),C.SkyLightCloudBottomVisibility);
        Common->SetNumberField(TEXT("TracingMaxDistance"),C.TracingMaxDistance);
        Common->SetNumberField(TEXT("TracingMaxDistanceMode"),C.TracingMaxDistanceMode);
        Common->SetNumberField(TEXT("TracingStartMaxDistance"),C.TracingStartMaxDistance);
        Common->SetNumberField(TEXT("TracingStartDistanceFromCamera"),C.TracingStartDistanceFromCamera);
        Common->SetArrayField(TEXT("CloudLayerCenterKm"),{MakeShared<FJsonValueNumber>(C.CloudLayerCenterKm.X),MakeShared<FJsonValueNumber>(C.CloudLayerCenterKm.Y),MakeShared<FJsonValueNumber>(C.CloudLayerCenterKm.Z)});
        Common->SetArrayField(TEXT("CloudShadowmapSampleCount"),{MakeShared<FJsonValueNumber>(C.CloudShadowmapSampleCount[0].X),MakeShared<FJsonValueNumber>(C.CloudShadowmapSampleCount[1].X)});
        Common->SetNumberField(TEXT("CloudSkyAOSampleCount"),C.CloudSkyAOSampleCount);
        CloudAudit->SetObjectField(TEXT("rendererCommon"),Common);
        TSharedRef<FJsonObject> P=MakeShared<FJsonObject>();
        P->SetNumberField(TEXT("ViewSampleCountScale"),Proxy.ViewSampleCountScale);
        P->SetNumberField(TEXT("ShadowViewSampleCountScale"),Proxy.ShadowViewSampleCountScale);
        P->SetNumberField(TEXT("ReflectionViewSampleCountScale"),Proxy.ReflectionViewSampleCountScale);
        P->SetNumberField(TEXT("ShadowReflectionViewSampleCountScale"),Proxy.ShadowReflectionViewSampleCountScale);
        P->SetNumberField(TEXT("ShadowTracingDistance"),Proxy.ShadowTracingDistance);
        P->SetBoolField(TEXT("visibleInRealTimeSkyCaptures"),Proxy.bVisibleInRealTimeSkyCaptures);
        P->SetBoolField(TEXT("renderInMainPass"),Proxy.bRenderInMainPass);
        P->SetBoolField(TEXT("perSampleAtmosphericLightTransmittance"),Proxy.bUsePerSampleAtmosphericLightTransmittance);
        CloudAudit->SetObjectField(TEXT("rendererProxy"),P);
        UMaterialInterface* MI=Proxy.GetCloudVolumeMaterial();
        const FMaterialRenderProxy* MaterialProxy=MI?MI->GetRenderProxy():nullptr;
        const FMaterial* Material=MaterialProxy?MaterialProxy->GetMaterialNoFallback(View.GetFeatureLevel()):nullptr;
        CloudAudit->SetBoolField(TEXT("materialNoFallbackPresent"),Material!=nullptr);
        if(Material)
        {
            CloudAudit->SetStringField(TEXT("renderMaterialFriendlyName"),Material->GetFriendlyName());
            CloudAudit->SetNumberField(TEXT("renderMaterialDomain"),static_cast<int32>(Material->GetMaterialDomain()));
            const FMaterialShaderMap* ShaderMap=Material->GetRenderingThreadShaderMap();
            CloudAudit->SetBoolField(TEXT("renderShaderMapPresent"),ShaderMap!=nullptr);
            CloudAudit->SetBoolField(TEXT("renderShaderMapValid"),ShaderMap&&ShaderMap->IsValidForRendering());
            CloudAudit->SetBoolField(TEXT("renderShaderMapComplete"),Material->IsRenderingThreadShaderMapComplete());
        }
    }
    FString CloudText;FJsonSerializer::Serialize(CloudAudit,TJsonWriterFactory<>::Create(&CloudText));
    FFileHelper::SaveStringToFile(CloudText,*(Stem+TEXT(".cloud-renderer.json")));
    TSharedRef<FJsonObject> Meta=MakeShared<FJsonObject>();
    Meta->SetNumberField(TEXT("worldSeconds"),View.Family->Time.GetWorldTimeSeconds()); Meta->SetNumberField(TEXT("frame"),View.Family->FrameNumber);
    Meta->SetNumberField(TEXT("worldSecondsAtSetup"),Seconds); Meta->SetNumberField(TEXT("frameAtSetup"),Frame);
    Meta->SetBoolField(TEXT("diagnosticPipesPresent"),true);
    Meta->SetBoolField(TEXT("eyeAdaptationShowFlag"),View.Family->EngineShowFlags.EyeAdaptation);
    Meta->SetBoolField(TEXT("colorGradingShowFlag"),View.Family->EngineShowFlags.ColorGrading);
    Meta->SetBoolField(TEXT("bloomShowFlag"),View.Family->EngineShowFlags.Bloom);
    Meta->SetBoolField(TEXT("vignetteShowFlag"),View.Family->EngineShowFlags.Vignette);
    Meta->SetNumberField(TEXT("displayGamma"),View.Family->RenderTarget?View.Family->RenderTarget->GetDisplayGamma():0);
    const FIntRect U=View.UnscaledViewRect;
    Meta->SetArrayField(TEXT("unscaledViewRect"),{MakeShared<FJsonValueNumber>(U.Min.X),MakeShared<FJsonValueNumber>(U.Min.Y),MakeShared<FJsonValueNumber>(U.Max.X),MakeShared<FJsonValueNumber>(U.Max.Y)});
    const FTextureRHIRef T=View.Family->RenderTarget?View.Family->RenderTarget->GetRenderTargetTexture():nullptr;
    Meta->SetNumberField(TEXT("mainOutputPixelFormat"),T.IsValid()?static_cast<int32>(T->GetFormat()):-1);

    Meta->SetBoolField(TEXT("hasViewState"),View.State!=nullptr);
    Meta->SetNumberField(TEXT("preExposure"),View.State ? View.State->GetPreExposure() : 1.f);
    Meta->SetBoolField(TEXT("tonemapperShowFlag"),View.Family->EngineShowFlags.Tonemapper);
    Meta->SetBoolField(TEXT("visualizeBufferShowFlag"),View.Family->EngineShowFlags.VisualizeBuffer);
    for (const TCHAR* Name : {TEXT("r.BufferVisualizationDumpFrames"),TEXT("r.BufferVisualizationDumpFramesAsHDR"),TEXT("r.ExposureOffset"),TEXT("r.EyeAdaptation.MethodOverride"),TEXT("r.HDR.EnableHDROutput"),TEXT("r.HDR.Display.OutputDevice"),TEXT("r.HDR.Display.ColorGamut"),TEXT("r.TonemapperGamma"),TEXT("r.BloomQuality"),TEXT("r.LensFlareQuality"),TEXT("r.Color.Grading"),TEXT("r.Tonemapper.Quality"),TEXT("r.Tonemapper.Sharpen"),TEXT("r.Tonemapper.GrainQuantization"),TEXT("r.VolumetricCloud.EnableDistantSkyLightSampling"),TEXT("r.VolumetricCloud.EnableAtmosphericLightsSampling"),TEXT("r.VolumetricCloud.EnableLocalLightsSampling"),TEXT("r.SkyLight.RealTimeReflectionCapture.TimeSlice"),TEXT("r.SkyLight.RealTimeReflectionCapture"),TEXT("r.VolumetricCloud.ShadowMap") })
        if (const IConsoleVariable* Var=IConsoleManager::Get().FindConsoleVariable(Name)) Meta->SetStringField(Name,Var->GetString());
    FString Text; FJsonSerializer::Serialize(Meta,TJsonWriterFactory<>::Create(&Text));
    FFileHelper::SaveStringToFile(Text,*(Stem+TEXT(".hdr-view.json")));
}


bool FWindowSkySampling::GetMeasurement(float& OutSkyFraction, FIntPoint& OutRenderSize) const
{
    FScopeLock Lock(&MeasurementLock);
    OutSkyFraction = SkyFraction;
    OutRenderSize = RenderSize;
    return SkyFraction >= 0;
}

void FWindowSkySampling::CopySkyMask(TArray<uint8>& OutMask, FIntPoint& OutMaskSize, bool& OutOnly) const
{
    FScopeLock Lock(&MeasurementLock);
    OutMask = SkyMask;
    OutMaskSize = SkyMask.Num() == SampleSize.X * SampleSize.Y ? SampleSize : FIntPoint::ZeroValue;
    OutOnly = bSkyMaskOnly;
}

void FWindowSkySampling::PostRenderBasePassDeferred_RenderThread(FRDGBuilder& GraphBuilder, FSceneView& View,
    const FRenderTargetBindingSlots& RenderTargets,
    TRDGUniformBufferRef<FSceneTextureUniformParameters> SceneTextures)
{
    if (!View.bIsGameView || View.bIsSceneCapture || View.bIsReflectionCapture || View.bIsPlanarReflection
        || !View.Family || View.Family->Views.IsEmpty() || View.Family->Views[0] != &View) return;

    if (bReadbackPending)
    {
        if (!Readback->IsReady()) return;
        int32 RowPitch = 0, BufferHeight = 0;
        const float* Depth = static_cast<const float*>(Readback->Lock(RowPitch, &BufferHeight));
        const float Fraction = BufferHeight >= SampleSize.Y ? WindowSkyFraction(Depth, SampleSize, RowPitch) : -1;
        TArray<uint8> Mask;
        bool bOnly = true;
        const bool bMasked = BufferHeight >= SampleSize.Y && WindowSkyMask(Depth, SampleSize, RowPitch, Mask, bOnly);
        if (Depth) Readback->Unlock();
        bReadbackPending = false;
        if (Fraction >= 0)
        {
            FScopeLock Lock(&MeasurementLock);
            SkyFraction = Fraction;
            RenderSize = PendingRenderSize;
            if (bMasked) { SkyMask = MoveTemp(Mask); bSkyMaskOnly = bOnly; }
        }
    }

    const double Now = FPlatformTime::Seconds();
    if (Now - LastRequestSeconds < 2) return;
    FRDGTextureRef Depth = RenderTargets.DepthStencil.GetTexture();
    // This callback receives FViewInfo: the public helper returns its actual scaled view rectangle.
    const FIntRect ViewRect = UE::FXRenderingUtils::GetRawViewRectUnsafe(View);
    if (!Depth || Depth->Desc.NumSamples != 1 || ViewRect.Width() <= 0 || ViewRect.Height() <= 0) return;

    if (!Readback) Readback = MakeUnique<FRHIGPUTextureReadback>(TEXT("WindowSkyArea"));
    FRDGTextureRef Samples = GraphBuilder.CreateTexture(FRDGTextureDesc::Create2D(SampleSize, PF_R32_FLOAT,
        FClearValueBinding::None, TexCreate_ShaderResource | TexCreate_RenderTargetable), TEXT("WindowSkyDepth"));
    // ponytail: fixed grid estimates opaque-depth sky coverage; raise the grid if thin silhouettes matter.
    AddDrawTexturePass(GraphBuilder, View, FScreenPassTexture(Depth, ViewRect),
        FScreenPassRenderTarget(Samples, ERenderTargetLoadAction::ENoAction));
    AddEnqueueCopyPass(GraphBuilder, Readback.Get(), Samples);
    PendingRenderSize = ViewRect.Size();
    LastRequestSeconds = Now;
    bReadbackPending = true;
}
