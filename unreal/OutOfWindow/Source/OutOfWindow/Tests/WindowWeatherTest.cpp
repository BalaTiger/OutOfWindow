#if WITH_DEV_AUTOMATION_TESTS

#include "../WindowWeather.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowWeatherTest, "OutOfWindow.Weather.Classification",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWindowWeatherTest::RunTest(const FString& Parameters)
{
    struct FCase { int32 Code; const TCHAR* Label; const TCHAR* Family; };
    const FCase Cases[] = {
        {0, TEXT("晴"), TEXT("clear")}, {1, TEXT("晴间多云"), TEXT("clear")},
        {2, TEXT("多云"), TEXT("cloudy")}, {3, TEXT("阴"), TEXT("overcast")},
        {45, TEXT("雾"), TEXT("fog")}, {48, TEXT("雾凇"), TEXT("fog")},
        {51, TEXT("毛毛雨（弱）"), TEXT("rain")}, {53, TEXT("毛毛雨（中）"), TEXT("rain")},
        {55, TEXT("毛毛雨（强）"), TEXT("rain")}, {56, TEXT("冻毛毛雨（弱）"), TEXT("rain")},
        {57, TEXT("冻毛毛雨（强）"), TEXT("rain")},
        {61, TEXT("小雨"), TEXT("rain")}, {63, TEXT("中雨"), TEXT("rain")},
        {65, TEXT("大雨"), TEXT("rain")}, {66, TEXT("小冻雨"), TEXT("rain")},
        {67, TEXT("大冻雨"), TEXT("rain")},
        {71, TEXT("小雪"), TEXT("snow")}, {73, TEXT("中雪"), TEXT("snow")},
        {75, TEXT("大雪"), TEXT("snow")}, {77, TEXT("米雪"), TEXT("snow")},
        {80, TEXT("小阵雨"), TEXT("rain")}, {81, TEXT("中阵雨"), TEXT("rain")},
        {82, TEXT("强阵雨"), TEXT("rain")}, {85, TEXT("小阵雪"), TEXT("snow")},
        {86, TEXT("大阵雪"), TEXT("snow")},
        {95, TEXT("雷暴"), TEXT("rain")}, {96, TEXT("雷暴伴冰雹（弱）"), TEXT("rain")},
        {97, TEXT("强雷暴"), TEXT("rain")}, {99, TEXT("雷暴伴冰雹（强）"), TEXT("rain")},
        {-1, TEXT("未知"), TEXT("unknown")}, {62, TEXT("未知"), TEXT("unknown")},
        {100, TEXT("未知"), TEXT("unknown")}
    };
    for (const FCase& Case : Cases)
    {
        TestEqual(FString::Printf(TEXT("WMO %d precise label"), Case.Code),
            FString(WindowWeather::LabelForCode(Case.Code)), FString(Case.Label));
        TestEqual(FString::Printf(TEXT("WMO %d render family"), Case.Code),
            FString(WindowWeather::FamilyForCode(Case.Code)), FString(Case.Family));
        const float Density = WindowWeather::PrecipitationIntensityForCode(Case.Code);
        const bool bPrecipitation = FString(Case.Family) == TEXT("rain") || FString(Case.Family) == TEXT("snow");
        TestTrue(TEXT("Only precipitation produces bounded particles"),
            bPrecipitation ? Density > 0.f && Density <= 1.f : Density == 0.f);
    }
    struct FPreview { const TCHAR* Mode; int32 Code; };
    const FPreview Previews[] = {
        {TEXT("clear"), 0}, {TEXT("cloudy"), 2}, {TEXT("overcast"), 3}, {TEXT("fog"), 45},
        {TEXT("light_rain"), 61}, {TEXT("moderate_rain"), 63}, {TEXT("heavy_rain"), 65},
        {TEXT("light_snow"), 71}, {TEXT("moderate_snow"), 73}, {TEXT("heavy_snow"), 75}
    };
    for (const FPreview& Preview : Previews)
    {
        TestEqual(TEXT("Preview remains valid after normalization"),
            WindowWeather::NormalizeMode(Preview.Mode), FString(Preview.Mode));
        TestEqual(TEXT("Preview shares the live classification"),
            WindowWeather::CodeForPreview(Preview.Mode), Preview.Code);
    }
    TestEqual(TEXT("Legacy rain alias"), WindowWeather::NormalizeMode(TEXT(" RAIN ")), FString(TEXT("moderate_rain")));
    TestEqual(TEXT("Legacy snow alias"), WindowWeather::NormalizeMode(TEXT("Snow")), FString(TEXT("moderate_snow")));
    TestEqual(TEXT("Live mode is accepted"), WindowWeather::NormalizeMode(TEXT("real")), FString(TEXT("real")));
    TestEqual(TEXT("Legacy live alias"), WindowWeather::NormalizeMode(TEXT("live")), FString(TEXT("real")));
    TestEqual(TEXT("Invalid preview rejected"), WindowWeather::NormalizeMode(TEXT("sandstorm")), FString());
    TestEqual(TEXT("Empty preview rejected"), WindowWeather::CodeForPreview(TEXT("")), -1);
    TestEqual(TEXT("Legacy rain code"), WindowWeather::CodeForPreview(TEXT("rain")), 63);
    TestEqual(TEXT("Legacy snow code"), WindowWeather::CodeForPreview(TEXT("snow")), 73);
    for (const int32 LightCode : {61, 71})
    {
        TestTrue(TEXT("Small to medium precipitation increases visual density"),
            WindowWeather::PrecipitationIntensityForCode(LightCode) < WindowWeather::PrecipitationIntensityForCode(LightCode + 2));
        TestTrue(TEXT("Medium to heavy precipitation increases visual density"),
            WindowWeather::PrecipitationIntensityForCode(LightCode + 2) < WindowWeather::PrecipitationIntensityForCode(LightCode + 4));
    }
    return true;
}

#endif
