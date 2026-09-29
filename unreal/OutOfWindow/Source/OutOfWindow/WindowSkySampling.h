#pragma once

#include "CoreMinimal.h"
#include "SceneViewExtension.h"

class FRHIGPUTextureReadback;

// Counts background pixels in a point-sampled reversed-Z depth buffer, respecting GPU row padding.
float WindowSkyFraction(const float* Depth, FIntPoint Size, int32 RowPitch);
float WindowCloudSampleScale(float VisibleSkyPixels, int32 Quality, float BudgetPixels);

class FWindowSkySampling : public FWorldSceneViewExtension
{
public:
    FWindowSkySampling(const FAutoRegister& AutoRegister, UWorld* World);
    virtual ~FWindowSkySampling() override;

    bool GetMeasurement(float& OutSkyFraction, FIntPoint& OutRenderSize) const;
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
};
