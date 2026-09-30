#pragma once

#include "CoreMinimal.h"
#include "SceneViewExtension.h"

class FRHIGPUTextureReadback;

// Counts background pixels in a point-sampled reversed-Z depth buffer, respecting GPU row padding.
float WindowSkyFraction(const float* Depth, FIntPoint Size, int32 RowPitch);
// Where those pixels are, as a 0/255 mask row-major at Size. Writes Size.X*Size.Y
// bytes and invalidates OutOnly. Empty geometry regions are sky: at base pass the
// far plane holds both open sky and the volumetric cloud deck.
bool WindowSkyMask(const float* Depth, FIntPoint Size, int32 RowPitch, TArray<uint8>& OutMask, bool& OutOnly);
float WindowCloudSampleScale(float VisibleSkyPixels, int32 Quality, float BudgetPixels);

class FWindowSkySampling : public FWorldSceneViewExtension
{
public:
    FWindowSkySampling(const FAutoRegister& AutoRegister, UWorld* World);
    virtual ~FWindowSkySampling() override;

    bool GetMeasurement(float& OutSkyFraction, FIntPoint& OutRenderSize) const;
    // Copies the last sampled sky mask for the capture writer; empty until the first readback.
    void CopySkyMask(TArray<uint8>& OutMask, FIntPoint& OutMaskSize, bool& OutOnly) const;
    virtual void PostRenderBasePassDeferred_RenderThread(FRDGBuilder& GraphBuilder, FSceneView& View,
        const FRenderTargetBindingSlots& RenderTargets,
        TRDGUniformBufferRef<FSceneTextureUniformParameters> SceneTextures) override;

private:
    TUniquePtr<FRHIGPUTextureReadback> Readback;
    bool bReadbackPending = false;
    double LastRequestSeconds = -2;
    FIntPoint PendingRenderSize = FIntPoint::ZeroValue;
    mutable FCriticalSection MeasurementLock;
    float SkyFraction = -1;
    FIntPoint RenderSize = FIntPoint::ZeroValue;
    TArray<uint8> SkyMask;
    bool bSkyMaskOnly = true;
};
