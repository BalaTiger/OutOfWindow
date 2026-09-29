#include "WindowSkySampling.h"

#include "FXRenderingUtils.h"
#include "HAL/PlatformTime.h"
#include "Misc/ScopeLock.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "RHIGPUReadback.h"
#include "ScreenPass.h"

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

bool FWindowSkySampling::GetMeasurement(float& OutSkyFraction, FIntPoint& OutRenderSize) const
{
    FScopeLock Lock(&MeasurementLock);
    OutSkyFraction = SkyFraction;
    OutRenderSize = RenderSize;
    return SkyFraction >= 0;
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
        if (Depth) Readback->Unlock();
        bReadbackPending = false;
        if (Fraction >= 0)
        {
            FScopeLock Lock(&MeasurementLock);
            SkyFraction = Fraction;
            RenderSize = PendingRenderSize;
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
