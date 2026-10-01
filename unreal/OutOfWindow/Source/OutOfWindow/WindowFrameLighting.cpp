#include "WindowFrameLighting.h"

#include "Components/LightComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/RectLightComponent.h"
#include "Components/SpotLightComponent.h"
#include "GameFramework/Actor.h"

namespace
{
bool HasUsableBounds(const FBox& Bounds)
{
    return Bounds.IsValid && !Bounds.Min.ContainsNaN() && !Bounds.Max.ContainsNaN()
        && Bounds.Min.X <= Bounds.Max.X && Bounds.Min.Y <= Bounds.Max.Y && Bounds.Min.Z <= Bounds.Max.Z;
}

bool HasDynamicShadow(ULightComponent* Light)
{
    return IsValid(Light) && Light->Mobility == EComponentMobility::Movable && Light->bAffectsWorld
        && Light->IsVisible() && Light->CastShadows && Light->CastDynamicShadows
        && Light->LightingChannels.bChannel0;
}
}

FWindowFrameLighting::~FWindowFrameLighting()
{
    Reset();
}

TArray<ULightComponent*> FWindowFrameLighting::SelectExteriorLights(FName Scene,
    const FVector& CameraLocation, const FBox& FrameBounds,
    const TArray<TObjectPtr<ULightComponent>>& NightLights)
{
    TArray<ULightComponent*> Result;
    if (Scene != TEXT("Alley") || CameraLocation.ContainsNaN() || !HasUsableBounds(FrameBounds)) return Result;

    struct FCandidate { ULightComponent* Light; double DistanceSquared; FString Path; };
    TArray<FCandidate> Candidates;
    TSet<ULightComponent*> Seen;
    for (ULightComponent* Light : NightLights)
    {
        if (!HasDynamicShadow(Light) || Seen.Contains(Light)) continue;
        Seen.Add(Light);
        AActor* Owner = Light->GetOwner();
        UPointLightComponent* Point = Cast<UPointLightComponent>(Light);
        if (!IsValid(Owner) || Owner->IsHidden() || !Owner->ActorHasTag(TEXT("OOWNightLight"))
            || Owner->ActorHasTag(TEXT("OOWInteriorLight")) || !Point || Light->IsA<USpotLightComponent>()) continue;

        const double Radius = Point->AttenuationRadius;
        const FVector Location = Light->GetComponentLocation();
        if (!FMath::IsFinite(Radius) || Radius <= 0 || Location.ContainsNaN()
            || !FMath::IsFinite(Point->SourceRadius) || Point->SourceRadius < 0
            || FrameBounds.ComputeSquaredDistanceToPoint(Location) > Radius * Radius) continue;
        const double DistanceSquared = FVector::DistSquared(CameraLocation, Location);
        if (FMath::IsFinite(DistanceSquared)) Candidates.Add({Light, DistanceSquared, Light->GetPathName()});
    }
    Candidates.Sort([](const FCandidate& A, const FCandidate& B)
    {
        // A path is only a stable tie break; no label, suffix or actor index determines eligibility.
        return A.DistanceSquared == B.DistanceSquared ? A.Path < B.Path : A.DistanceSquared < B.DistanceSquared;
    });
    for (int32 Index = 0; Index < FMath::Min(MaxExteriorLights, Candidates.Num()); ++Index)
        Result.Add(Candidates[Index].Light);
    return Result;
}

void FWindowFrameLighting::Restore(const FManagedLight& Entry)
{
    if (ULightComponent* Light = Entry.Light.Get())
    {
        if (Light->CastRaytracedShadow != Entry.OriginalMode) Light->SetCastRaytracedShadows(Entry.OriginalMode);
        if (Entry.OriginalSourceRadius.IsSet())
        {
            if (UPointLightComponent* Point = Cast<UPointLightComponent>(Light))
            {
                if (Point->SourceRadius != Entry.OriginalSourceRadius.GetValue()) Point->SetSourceRadius(Entry.OriginalSourceRadius.GetValue());
            }
        }
        else if (Light->SamplesPerPixel != Entry.OriginalSamplesPerPixel)
            Light->SetSamplesPerPixel(Entry.OriginalSamplesPerPixel);
    }
}

void FWindowFrameLighting::Reset()
{
    for (const FManagedLight& Entry : ManagedLights) Restore(Entry);
    ManagedLights.Reset();
}

void FWindowFrameLighting::Update(FName Scene, const FVector& CameraLocation, const FBox& FrameBounds,
    const TArray<TObjectPtr<ULightComponent>>& NightLights, URectLightComponent* IndoorLight,
    int32 Quality, bool bRayTracingAvailable)
{
    if (CameraLocation.ContainsNaN() || !HasUsableBounds(FrameBounds))
    {
        Reset();
        return;
    }
    TArray<ULightComponent*> Targets = SelectExteriorLights(Scene, CameraLocation, FrameBounds, NightLights);
    if (HasDynamicShadow(IndoorLight) && FMath::IsFinite(IndoorLight->SourceWidth) && IndoorLight->SourceWidth > 0
        && FMath::IsFinite(IndoorLight->SourceHeight) && IndoorLight->SourceHeight > 0)
        Targets.AddUnique(IndoorLight);

    for (int32 Index = ManagedLights.Num() - 1; Index >= 0; --Index)
    {
        if (!ManagedLights[Index].Light.IsValid() || !Targets.Contains(ManagedLights[Index].Light.Get()))
        {
            Restore(ManagedLights[Index]);
            ManagedLights.RemoveAt(Index);
        }
    }
    const int32 Tier = FMath::Clamp(Quality, 0, 2);
    const bool bUseRayTracing = Tier > 0 && bRayTracingAvailable;
    for (ULightComponent* Light : Targets)
    {
        FManagedLight* Entry = ManagedLights.FindByPredicate([Light](const FManagedLight& Item) { return Item.Light.Get() == Light; });
        if (!Entry)
        {
            FManagedLight Original;
            Original.Light = Light;
            Original.OriginalMode = Light->CastRaytracedShadow;
            Original.OriginalSamplesPerPixel = Light->SamplesPerPixel;
            if (UPointLightComponent* Point = Cast<UPointLightComponent>(Light)) Original.OriginalSourceRadius = Point->SourceRadius;
            Entry = &ManagedLights.Add_GetRef(Original);
        }
        // Exterior RT exposes a different Nanite shadow representation for the
        // neighboring awning. Keep that source on the verified VSM path, and widen
        // its finite source without changing energy, bias, SPP, or lamp placement.
        const bool bIndoorRayTracing = bUseRayTracing && !Entry->OriginalSourceRadius.IsSet();
        const ECastRayTracedShadow::Type Mode = bIndoorRayTracing ? ECastRayTracedShadow::Enabled : ECastRayTracedShadow::Disabled;
        if (Light->CastRaytracedShadow != Mode) Light->SetCastRaytracedShadows(Mode);
        if (Entry->OriginalSourceRadius.IsSet())
        {
            if (UPointLightComponent* Point = Cast<UPointLightComponent>(Light))
            {
                const float Radius = FMath::Max(Entry->OriginalSourceRadius.GetValue(), MinimumExteriorSourceRadius);
                if (Point->SourceRadius != Radius) Point->SetSourceRadius(Radius);
            }
        }
        else
        {
            const int32 Samples = bIndoorRayTracing ? (Tier == 1 ? 2 : 4) : Entry->OriginalSamplesPerPixel;
            if (Light->SamplesPerPixel != Samples) Light->SetSamplesPerPixel(Samples);
        }
    }
}
