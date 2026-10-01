#pragma once

#include "CoreMinimal.h"
#include "Components/LightComponentBase.h"

class ULightComponent;
class URectLightComponent;

// Bounded, reversible foreground lighting: soften one exterior point source with
// VSM, and optionally use area RT for the indoor rectangle. Scene energy, lighting
// channels, geometry, GI, and global renderer settings remain authored.
class FWindowFrameLighting
{
public:
    static constexpr int32 MaxExteriorLights = 1;
    static constexpr float MinimumExteriorSourceRadius = 24.f; // UE centimetres.

    FWindowFrameLighting() = default;
    ~FWindowFrameLighting();
    FWindowFrameLighting(const FWindowFrameLighting&) = delete;
    FWindowFrameLighting& operator=(const FWindowFrameLighting&) = delete;

    // FrameBounds must describe the visible frame mesh, excluding its attached room
    // walls. Exterior shadows stay on VSM at every quality, with at least a 24 cm
    // source radius; larger authored sources are preserved. Hardware availability
    // only gates the optional room RectLight's RT path. That explicit caller-owned
    // local rectangle can use the same quality policy in every scene.
    // Call after binding the camera/frame, and again after quality or scene changes.
    void Update(FName Scene, const FVector& CameraLocation, const FBox& FrameBounds,
        const TArray<TObjectPtr<ULightComponent>>& NightLights, URectLightComponent* IndoorLight,
        int32 Quality, bool bRayTracingAvailable);

    // Restores the settings captured before this policy first touched each light.
    void Reset();
    int32 GetManagedLightCount() const { return ManagedLights.Num(); }

    // Point sources are the only exterior category confirmed by the Alley diagnosis.
    // Ignore interior/spot lights, invalid bounds and lights whose sphere misses the
    // actual foreground. Distance ordering is independent of scene actor numbering.
    static TArray<ULightComponent*> SelectExteriorLights(FName Scene, const FVector& CameraLocation,
        const FBox& FrameBounds, const TArray<TObjectPtr<ULightComponent>>& NightLights);

private:
    struct FManagedLight
    {
        TWeakObjectPtr<ULightComponent> Light;
        ECastRayTracedShadow::Type OriginalMode = ECastRayTracedShadow::UseProjectSetting;
        int32 OriginalSamplesPerPixel = 1;
        // Only point sources alter their radius; only the room rectangle alters SPP.
        TOptional<float> OriginalSourceRadius;
    };
    TArray<FManagedLight> ManagedLights;
    static void Restore(const FManagedLight& Entry);
};
