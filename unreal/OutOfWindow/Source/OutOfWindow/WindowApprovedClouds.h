#pragma once
#include "CoreMinimal.h"

// Input is AWindowDirector::ActualWeather(), the same resolved state used by the UI.
// Provider codes/cloud amounts are never independently reinterpreted here.
namespace WindowApprovedClouds
{
struct FTarget
{
    float Lightweight = 0;
    float Cirrus = 0;
    float RainProfile = 0;
};
inline FTarget Targets(const FString& DisplayedWeather)
{
    if (DisplayedWeather == TEXT("clear")) return {0, 1, 0};
    if (DisplayedWeather == TEXT("few")) return {0, .55f, 0};
    if (DisplayedWeather == TEXT("cloudy")) return {1, .15f, 0};
    if (DisplayedWeather == TEXT("overcast")) return {1, 0, 1};
    if (DisplayedWeather == TEXT("rain")) return {1, 0, 1};
    // Snow/fog/unknown keep their existing low cloud route; no new semantics.
    return {0, 0, 0};
}
}
