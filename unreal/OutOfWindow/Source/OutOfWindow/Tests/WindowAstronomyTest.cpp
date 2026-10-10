#if WITH_DEV_AUTOMATION_TESTS
#include "../WindowAstronomy.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowAstronomyTest, "OutOfWindow.Lighting.Astronomy",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWindowAstronomyTest::RunTest(const FString& Parameters)
{
    // Independent numeric example from Schlyter's lunar tutorial.
    const auto Example = WindowAstronomy::MoonPosition(FDateTime(1990, 4, 19), 60., 15., 0.);
    TestTrue(TEXT("Lunar topocentric altitude matches published example"), FMath::Abs(Example.ElevationDegrees + 16.226) < .1);
    TestTrue(TEXT("Lunar azimuth matches published example"), FMath::Abs(FMath::RadiansToDegrees(Example.AzimuthRadians) - 101.782) < .1);
    TestTrue(TEXT("Lunar perturbations preserve published distance"), FMath::Abs(Example.DistanceEarthRadii - 60.6779) < .01);
    const auto Dusk = WindowAstronomy::SolarPosition(FDateTime(2026, 10, 5, 17, 36), 31.23, 121.47, 28800.);
    const double Alt = FMath::RadiansToDegrees(Dusk.ElevationRadians);
    TestTrue(TEXT("Shanghai 17:36 is sunset twilight, not astronomical night"), Alt > -6. && Alt < 0.);
    const auto Full = WindowAstronomy::MoonPosition(FDateTime(2026, 9, 26, 23), 31.23, 121.47, 28800.);
    const auto Below = WindowAstronomy::MoonPosition(FDateTime(2026, 10, 5, 20), 31.23, 121.47, 28800.);
    TestTrue(TEXT("Full moon validation date has bright moon above horizon"), Full.ElevationDegrees > 55. && Full.IlluminatedFraction > .99);
    TestTrue(TEXT("Shanghai October 5 evening has moon below horizon"), Below.ElevationDegrees < 0.);
    const auto UTC = WindowAstronomy::MoonPosition(FDateTime(2026, 9, 26, 15), 31.23, 121.47, 0.);
    TestTrue(TEXT("UTC and local civil time resolve the same lunar position"), UTC.Direction.Equals(Full.Direction, 1e-8));
    for (double Lat : {-90., 0., 90.})
    {
        const auto Pole = WindowAstronomy::MoonPosition(FDateTime(2026, 10, 6, 2), Lat, 121.47, 28800.);
        TestTrue(TEXT("Polar lunar direction remains finite and normalized"), !Pole.Direction.ContainsNaN() && Pole.Direction.IsUnit());
    }
    return true;
}
#endif
