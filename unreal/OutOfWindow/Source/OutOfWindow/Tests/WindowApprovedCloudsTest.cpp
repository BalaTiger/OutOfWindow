#if WITH_DEV_AUTOMATION_TESTS
#include "../WindowApprovedClouds.h"
#include "../WindowWeather.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowApprovedCloudsTest, "OutOfWindow.Weather.ApprovedCloudRouting",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FWindowApprovedCloudsTest::RunTest(const FString& Parameters)
{
    struct FCase { double Cover; const TCHAR* Mode; float Low; float Ci; };
    const FCase Cases[] = {{24.9,TEXT("clear"),0,1},{25,TEXT("few"),0,.55f},
        {54.9,TEXT("few"),0,.55f},{55,TEXT("cloudy"),1,.15f},
        {84.9,TEXT("cloudy"),1,.15f},{85,TEXT("overcast"),1,0}};
    for (const auto& C : Cases)
    {
        const FString Displayed = WindowWeather::CloudMode(C.Cover);
        TestEqual(TEXT("Same displayed weather classification"), Displayed, FString(C.Mode));
        const auto T = WindowApprovedClouds::Targets(Displayed);
        TestEqual(TEXT("Accepted low target"), T.Lightweight, C.Low);
        TestEqual(TEXT("Accepted Ci target"), T.Cirrus, C.Ci);
        TestEqual(TEXT("Low routes are mutually exclusive"), T.Lightweight + (1.f-T.Lightweight), 1.f);
    }
    const auto Rain = WindowApprovedClouds::Targets(WindowWeather::FamilyForCode(63));
    TestEqual(TEXT("Provider rain retains rain route regardless of cloud amount"), Rain.RainProfile, 1.f);
    TestEqual(TEXT("Snow retains legacy near route"), WindowApprovedClouds::Targets(TEXT("snow")).Lightweight, 0.f);
    return true;
}
#endif
