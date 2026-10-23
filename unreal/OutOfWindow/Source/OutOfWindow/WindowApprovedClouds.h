#pragma once
#include "CoreMinimal.h"

// Input is AWindowDirector::ActualWeather(), the same resolved state used by the UI.
// Provider codes/cloud amounts are never independently reinterpreted here.
namespace WindowApprovedClouds
{
constexpr float FewNearKm = 4.f;
constexpr float FewFarKm = 8.f;

struct FTarget
{
    float Lightweight = 0;
    float Cirrus = 0;
    float RainProfile = 0;
    float FewFarLightweight = 0;
};
inline FTarget Targets(const FString& DisplayedWeather)
{
    if (DisplayedWeather == TEXT("clear")) return {0, 1, 0};
    if (DisplayedWeather == TEXT("few")) return {0, .55f, 0, 1};
    if (DisplayedWeather == TEXT("cloudy")) return {1, .15f, 0};
    if (DisplayedWeather == TEXT("overcast")) return {1, 0, 1};
    if (DisplayedWeather == TEXT("rain")) return {1, 0, 1};
    // Snow/fog/unknown keep their existing low cloud route; no new semantics.
    return {0, 0, 0};
}

struct FLowWeights
{
    float Lightweight;
    float Legacy;
};
// Mirrors the v2 material contract for capture diagnostics. Distance is horizontal
// from the fixed scene-camera origin, so reflection/shadow views use the same field.
inline FLowWeights LowWeights(float Lightweight, float FewFarLightweight, float HorizontalDistanceKm)
{
    const float T = FMath::Clamp((HorizontalDistanceKm - FewNearKm) / (FewFarKm - FewNearKm), 0.f, 1.f);
    const float Far = FMath::Clamp(FewFarLightweight, 0.f, 1.f) * T * T * (3.f - 2.f * T);
    const float Low = FMath::Lerp(FMath::Clamp(Lightweight, 0.f, 1.f), 1.f, Far);
    return {Low, 1.f - Low};
}
inline float Coverage(float RainProfile, float FewFarLightweight)
{
    return FMath::Lerp(FMath::Lerp(.48f, .69f, RainProfile), .26f, FewFarLightweight);
}
}
