#if WITH_DEV_AUTOMATION_TESTS

#include "../WindowWeather.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowWeatherTest, "OutOfWindow.Weather.Classification",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWindowWeatherTest::RunTest(const FString& Parameters)
{
    struct FCase { int32 Code; const TCHAR* Label; const TCHAR* Family; };
    const FCase Cases[] = {
        {0, TEXT("晴"), TEXT("clear")}, {1, TEXT("大致晴朗"), TEXT("clear")},
        {2, TEXT("局部多云"), TEXT("cloudy")}, {3, TEXT("阴"), TEXT("overcast")},
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
        {TEXT("clear"), 0}, {TEXT("few"), 1}, {TEXT("cloudy"), 2}, {TEXT("overcast"), 3}, {TEXT("fog"), 45},
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
    // An injected weather code must move the cloud amount, not just the label.
    struct FCode { int32 Code; double Cover; };
    const FCode Covers[] = {{0, 10}, {1, 40}, {2, 70}, {3, 100}, {45, 90}, {48, 90}};
    for (const FCode& Case : Covers)
        TestEqual(FString::Printf(TEXT("WMO %d reported cloud cover"), Case.Code),
            WindowWeather::DefaultCloudCoverForCode(Case.Code), Case.Cover);
    for (const int32 Rainy : {61, 71, 95})
        TestTrue(TEXT("Precip codes keep a near-overcast deck"),
            WindowWeather::DefaultCloudCoverForCode(Rainy) >= 90.);
    TestTrue(TEXT("Fair codes demote monotonically to the overcast deck"),
        WindowWeather::DefaultCloudCoverForCode(0) < WindowWeather::DefaultCloudCoverForCode(1) &&
        WindowWeather::DefaultCloudCoverForCode(1) < WindowWeather::DefaultCloudCoverForCode(2) &&
        WindowWeather::DefaultCloudCoverForCode(2) < WindowWeather::DefaultCloudCoverForCode(3) &&
        WindowWeather::DefaultCloudCoverForCode(3) > WindowWeather::DefaultCloudCoverForCode(2));
    for (const int32 LightCode : {61, 71})
    {
        TestTrue(TEXT("Small to medium precipitation increases visual density"),
            WindowWeather::PrecipitationIntensityForCode(LightCode) < WindowWeather::PrecipitationIntensityForCode(LightCode + 2));
        TestTrue(TEXT("Medium to heavy precipitation increases visual density"),
            WindowWeather::PrecipitationIntensityForCode(LightCode + 2) < WindowWeather::PrecipitationIntensityForCode(LightCode + 4));
    }
    struct FCloudCase { double Percent; int32 Tenths; const TCHAR* Label; };
    const FCloudCase CloudCases[] = {{0,0,TEXT("晴")}, {20,2,TEXT("晴")}, {24.999,2,TEXT("晴")},
        {25,3,TEXT("少云")}, {50,5,TEXT("少云")}, {54.999,5,TEXT("少云")},
        {55,6,TEXT("多云")}, {80,8,TEXT("多云")}, {84.999,8,TEXT("多云")}, {85,9,TEXT("阴")}, {100,10,TEXT("阴")}};
    for (const auto& Case : CloudCases)
    {
        TestEqual(TEXT("Continuous cover rounds to tenths"), WindowWeather::CloudAmountTenths(Case.Percent), Case.Tenths);
        TestEqual(TEXT("Chinese cloud label uses the same rounded cover"), FString(WindowWeather::CloudLabel(Case.Percent)), FString(Case.Label));
    }
    TestEqual(TEXT("Clear preview is ten percent, not twenty-five"), WindowWeather::PresetCloudCover(TEXT("clear")), 10.);
    TestEqual(TEXT("Few-cloud preview is forty percent"), WindowWeather::PresetCloudCover(TEXT("few")), 40.);
    TestEqual(TEXT("Cloudy preview is seventy percent"), WindowWeather::PresetCloudCover(TEXT("cloudy")), 70.);
    TestEqual(TEXT("Overcast preview is complete cover"), WindowWeather::PresetCloudCover(TEXT("overcast")), 100.);
    return true;
}

#endif
