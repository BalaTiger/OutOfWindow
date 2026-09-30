#if WITH_DEV_AUTOMATION_TESTS

#include "../WindowSkySampling.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowSkySamplingTest, "OutOfWindow.SkySampling.DepthCoverage",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWindowSkySamplingTest::RunTest(const FString& Parameters)
{
    const float Depth[] = {0, .4f, 0, 0, .00001f, 0, 0, 0};
    TestEqual(TEXT("Padding must not count as sky"), WindowSkyFraction(Depth, FIntPoint(2, 2), 4), .5f);
    TestEqual(TEXT("Open sky"), WindowSkyFraction(Depth, FIntPoint(1, 1), 4), 1.f);
    TestEqual(TEXT("Opaque surface, including distant geometry"), WindowSkyFraction(Depth + 4, FIntPoint(1, 1), 4), 0.f);
    TestEqual(TEXT("Missing readback"), WindowSkyFraction(nullptr, FIntPoint(2, 2), 4), -1.f);
    TestEqual(TEXT("Invalid row stride"), WindowSkyFraction(Depth, FIntPoint(2, 2), 1), -1.f);
    {
        TArray<uint8> Mask;
        bool bOnly = false;
        TestTrue(TEXT("Mask reads the same depth buffer"), WindowSkyMask(Depth, FIntPoint(2, 2), 4, Mask, bOnly));
        TestEqual(TEXT("Mask keeps padding out"), Mask.Num(), 4);
        TestEqual(TEXT("Mask marks open cells white"), static_cast<int32>(Mask[0]), 255);
        TestEqual(TEXT("Mask marks geometry black"), static_cast<int32>(Mask[1]), 0);
        TestEqual(TEXT("Mixed sky is not all-sky"), bOnly, false);
        TArray<uint8> AllSky;
        TestTrue(TEXT("All-sky buffer yields all-sky flag"), WindowSkyMask(Depth + 2, FIntPoint(1, 1), 4, AllSky, bOnly));
        TestTrue(TEXT("All-sky flag set"), bOnly);
        TestFalse(TEXT("A null buffer produces no mask"), WindowSkyMask(nullptr, FIntPoint(2, 2), 4, AllSky, bOnly));
    }
    TestEqual(TEXT("Small sky gets extra samples"), WindowCloudSampleScale(50000, 1, 200000), 2.f);
    TestEqual(TEXT("Area budget is continuous between caps"), WindowCloudSampleScale(160000, 1, 200000), 1.25f);
    TestEqual(TEXT("Large sky keeps the quality floor"), WindowCloudSampleScale(1000000, 1, 200000), 1.f);
    TestEqual(TEXT("Hidden sky and initial readback use the floor"), WindowCloudSampleScale(0, 1, 200000), 1.f);
    TestEqual(TEXT("Unavailable measurement is safe"), WindowCloudSampleScale(-1, 1, 200000), 1.f);
    TestTrue(TEXT("More rendered pixels reduce samples within budget"),
        WindowCloudSampleScale(160000, 1, 200000) < WindowCloudSampleScale(80000, 1, 200000));
    TestEqual(TEXT("Eco sampling remains bounded"), WindowCloudSampleScale(1, 0, 200000), 1.f);
    TestEqual(TEXT("Fine sampling remains bounded"), WindowCloudSampleScale(1, 2, 200000), 3.f);
    return true;
}

#endif
