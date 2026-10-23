#if WITH_DEV_AUTOMATION_TESTS
#include "../WindowApprovedClouds.h"
#include "../WindowWeather.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowApprovedCloudsTest, "OutOfWindow.Weather.ApprovedCloudRouting",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FWindowApprovedCloudsTest::RunTest(const FString& Parameters)
{
    struct FCase { double Cover; const TCHAR* Mode; float Low; float Ci; float FewFar; };
    const FCase Cases[] = {{24.9,TEXT("clear"),0,1,0},{25,TEXT("few"),0,.55f,1},
        {54.9,TEXT("few"),0,.55f,1},{55,TEXT("cloudy"),1,.15f,0},
        {84.9,TEXT("cloudy"),1,.15f,0},{85,TEXT("overcast"),1,0,0}};
    for (const auto& C : Cases)
    {
        const FString Displayed = WindowWeather::CloudMode(C.Cover);
        TestEqual(TEXT("Same displayed weather classification"), Displayed, FString(C.Mode));
        const auto T = WindowApprovedClouds::Targets(Displayed);
        TestEqual(TEXT("Accepted low target"), T.Lightweight, C.Low);
        TestEqual(TEXT("Accepted Ci target"), T.Cirrus, C.Ci);
        TestEqual(TEXT("Few-only distant lightweight target"), T.FewFarLightweight, C.FewFar);
        TestEqual(TEXT("Near field preserves weather route"), WindowApprovedClouds::LowWeights(T.Lightweight, T.FewFarLightweight, 4.f).Lightweight, C.Low);
        TestEqual(TEXT("Far field selects lightweight for few/cloudy/overcast"), WindowApprovedClouds::LowWeights(T.Lightweight, T.FewFarLightweight, 8.f).Lightweight, C.Low + C.FewFar);
    }
    const auto Rain = WindowApprovedClouds::Targets(WindowWeather::FamilyForCode(63));
    TestEqual(TEXT("Provider rain retains rain route regardless of cloud amount"), Rain.RainProfile, 1.f);
    TestEqual(TEXT("Rain remains full lightweight"), Rain.Lightweight, 1.f);
    TestEqual(TEXT("Rain has no few-only distance mask"), Rain.FewFarLightweight, 0.f);
    for (const TCHAR* Weather : {TEXT("snow"), TEXT("fog"), TEXT("unknown")})
    {
        const auto T = WindowApprovedClouds::Targets(Weather);
        TestEqual(TEXT("Other weather retains legacy near route"), T.Lightweight, 0.f);
        TestEqual(TEXT("Other weather retains legacy far route"), T.FewFarLightweight, 0.f);
    }
    TestEqual(TEXT("Few lightweight coverage stays sparse"), WindowApprovedClouds::Coverage(0.f, 1.f), .26f);
    TestEqual(TEXT("Cloudy retains accepted coverage"), WindowApprovedClouds::Coverage(0.f, 0.f), .48f);
    TestEqual(TEXT("Rain retains accepted coverage"), WindowApprovedClouds::Coverage(1.f, 0.f), .69f);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowApprovedCloudDistanceTest, "OutOfWindow.Weather.ApprovedCloudDistanceBlend",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FWindowApprovedCloudDistanceTest::RunTest(const FString& Parameters)
{
    struct FCase { float Distance; float Low; };
    const FCase Cases[] = {{0.f,0.f},{4.f,0.f},{5.f,.15625f},{6.f,.5f},{7.f,.84375f},{8.f,1.f},{12.f,1.f}};
    for (const auto& C : Cases)
    {
        const auto W = WindowApprovedClouds::LowWeights(0.f, 1.f, C.Distance);
        TestEqual(TEXT("Few field matches smooth distance transition"), W.Lightweight, C.Low);
        TestEqual(TEXT("Legacy and lightweight remain complementary"), W.Legacy, 1.f - C.Low);
        const auto Cloudy = WindowApprovedClouds::LowWeights(1.f, 0.f, C.Distance);
        TestEqual(TEXT("Cloudy has no near hole"), Cloudy.Lightweight, 1.f);
        const auto Legacy = WindowApprovedClouds::LowWeights(0.f, 0.f, C.Distance);
        TestEqual(TEXT("V1/other weather stays legacy at every distance"), Legacy.Legacy, 1.f);
    }
    // During a few -> cloudy transition, neither route may double-count the far field.
    const auto Near = WindowApprovedClouds::LowWeights(.5f, .5f, 4.f);
    const auto Middle = WindowApprovedClouds::LowWeights(.5f, .5f, 6.f);
    const auto Far = WindowApprovedClouds::LowWeights(.5f, .5f, 8.f);
    TestEqual(TEXT("Weather transition near contribution"), Near.Lightweight, .5f);
    TestEqual(TEXT("Weather transition middle contribution"), Middle.Lightweight, .625f);
    TestEqual(TEXT("Weather transition far contribution"), Far.Lightweight, .75f);
    TestEqual(TEXT("Weather transition keeps a complementary legacy contribution"), Far.Legacy, .25f);
    return true;
}
#endif
