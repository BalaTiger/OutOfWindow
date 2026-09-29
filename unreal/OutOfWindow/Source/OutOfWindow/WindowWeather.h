#pragma once

#include "CoreMinimal.h"

namespace WindowWeather
{
// Open-Meteo WMO interpretation: https://open-meteo.com/en/docs#weathervariables
inline const TCHAR* LabelForCode(int32 Code)
{
    switch (Code)
    {
    case 0: return TEXT("晴");
    case 1: return TEXT("晴间多云");
    case 2: return TEXT("多云");
    case 3: return TEXT("阴");
    case 45: return TEXT("雾");
    case 48: return TEXT("雾凇");
    case 51: return TEXT("毛毛雨（弱）");
    case 53: return TEXT("毛毛雨（中）");
    case 55: return TEXT("毛毛雨（强）");
    case 56: return TEXT("冻毛毛雨（弱）");
    case 57: return TEXT("冻毛毛雨（强）");
    case 61: return TEXT("小雨");
    case 63: return TEXT("中雨");
    case 65: return TEXT("大雨");
    case 66: return TEXT("小冻雨");
    case 67: return TEXT("大冻雨");
    case 71: return TEXT("小雪");
    case 73: return TEXT("中雪");
    case 75: return TEXT("大雪");
    case 77: return TEXT("米雪");
    case 80: return TEXT("小阵雨");
    case 81: return TEXT("中阵雨");
    case 82: return TEXT("强阵雨");
    case 85: return TEXT("小阵雪");
    case 86: return TEXT("大阵雪");
    case 95: return TEXT("雷暴");
    case 96: return TEXT("雷暴伴冰雹（弱）");
    case 97: return TEXT("强雷暴");
    case 99: return TEXT("雷暴伴冰雹（强）");
    default: return TEXT("未知");
    }
}

inline const TCHAR* FamilyForCode(int32 Code)
{
    switch (Code)
    {
    case 0: case 1: return TEXT("clear");
    case 2: return TEXT("cloudy");
    case 3: return TEXT("overcast");
    case 45: case 48: return TEXT("fog");
    case 51: case 53: case 55: case 56: case 57: case 61: case 63: case 65:
    case 66: case 67: case 80: case 81: case 82: case 95: case 96: case 97: case 99:
        return TEXT("rain");
    case 71: case 73: case 75: case 77: case 85: case 86: return TEXT("snow");
    default: return TEXT("unknown");
    }
}

inline int32 CodeForPreview(const FString& Mode)
{
    if (Mode == TEXT("clear")) return 0;
    if (Mode == TEXT("cloudy")) return 2;
    if (Mode == TEXT("overcast")) return 3;
    if (Mode == TEXT("fog")) return 45;
    if (Mode == TEXT("light_rain")) return 61;
    if (Mode == TEXT("moderate_rain") || Mode == TEXT("rain")) return 63;
    if (Mode == TEXT("heavy_rain")) return 65;
    if (Mode == TEXT("light_snow")) return 71;
    if (Mode == TEXT("moderate_snow") || Mode == TEXT("snow")) return 73;
    if (Mode == TEXT("heavy_snow")) return 75;
    return -1;
}

inline FString NormalizeMode(const FString& Mode)
{
    FString Normalized = Mode.TrimStartAndEnd().ToLower();
    if (Normalized == TEXT("live")) Normalized = TEXT("real");
    if (Normalized == TEXT("rain")) Normalized = TEXT("moderate_rain");
    if (Normalized == TEXT("snow")) Normalized = TEXT("moderate_snow");
    return Normalized == TEXT("real") || CodeForPreview(Normalized) >= 0 ? Normalized : FString();
}

// Visual particle density, not a precipitation measurement or an intensity threshold.
inline float PrecipitationIntensityForCode(int32 Code)
{
    switch (Code)
    {
    case 51: case 56: return .15f;
    case 53: case 61: case 66: case 71: case 77: case 80: case 85: return .3f;
    case 55: case 57: return .45f;
    case 63: case 73: case 81: case 95: case 96: return .65f;
    case 65: case 67: case 75: case 82: case 86: case 97: case 99: return 1.f;
    default: return 0.f;
    }
}
}
