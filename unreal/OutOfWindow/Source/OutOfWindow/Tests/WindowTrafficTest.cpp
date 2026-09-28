#if WITH_DEV_AUTOMATION_TESTS

#include "../WindowTraffic.h"
#include "Misc/AutomationTest.h"
#include <limits>

namespace
{
void AddCar(FWindowTraffic& Traffic, int32 Id, float Position, int32 Lane, float Speed, float DesiredSpeed, float Cooldown = 0)
{
    FWindowTrafficCar& Car = Traffic.Cars.AddDefaulted_GetRef();
    Car.Id = Id;
    Car.Direction = -1;
    Car.Position = Position;
    Car.Lane = Car.TargetLane = Lane;
    Car.Speed = Speed;
    Car.DesiredSpeed = DesiredSpeed;
    Car.Cooldown = Cooldown;
}

bool CheckTraffic(FAutomationTestBase& Test, const FWindowTraffic& Traffic, const TCHAR* Scenario, int32 Frame)
{
    for (int32 Index = 0; Index < Traffic.Cars.Num(); ++Index)
    {
        const FWindowTrafficCar& Car = Traffic.Cars[Index];
        if (!FMath::IsFinite(Car.Position) || !FMath::IsFinite(Car.Speed) || !FMath::IsFinite(Car.ChangeTime)
            || !FMath::IsFinite(Car.Cooldown) || Car.Position < 0 || Car.Position >= FWindowTraffic::RoadLength
            || Car.Speed < 0 || Car.Lane < 0 || Car.Lane > 1 || Car.TargetLane < 0 || Car.TargetLane > 1
            || Traffic.Location(Car, 695).ContainsNaN() || !FMath::IsFinite(Traffic.Yaw(Car)))
        {
            Test.AddError(FString::Printf(TEXT("%s frame %d: invalid state for car %d"), Scenario, Frame, Car.Id));
            return false;
        }
        for (int32 OtherIndex = Index + 1; OtherIndex < Traffic.Cars.Num(); ++OtherIndex)
        {
            const FWindowTrafficCar& Other = Traffic.Cars[OtherIndex];
            if (Car.Direction != Other.Direction || !((Car.Occupies(0) && Other.Occupies(0))
                || (Car.Occupies(1) && Other.Occupies(1)))) continue;
            const float Gap = FMath::Min(Traffic.Gap(Car, Other), Traffic.Gap(Other, Car));
            if (Gap < FWindowTraffic::MinimumGap - .001f)
            {
                Test.AddError(FString::Printf(TEXT("%s frame %d: cars %d/%d have %.4f m gap in a reserved lane"),
                    Scenario, Frame, Car.Id, Other.Id, Gap));
                return false;
            }
        }
    }
    return true;
}

FWindowTraffic CityTraffic()
{
    FWindowTraffic Traffic;
    // The sixteen tagged sedans placed by build_city_lookdev.py, in reverse discovery order.
    for (int32 Id = 15; Id >= 0; --Id)
    {
        const float X = (Id % 4 < 2 ? 220.f : 520.f) * (Id % 2 == 0 ? 1.f : -1.f);
        const float Y = 1100.f - ((Id * 1337) % 20400);
        Traffic.Add(Id, FVector(X, Y, 695));
    }
    return Traffic;
}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowTrafficBehaviourTest, "OutOfWindow.City.TrafficBehaviour",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWindowTrafficBehaviourTest::RunTest(const FString& Parameters)
{
    constexpr float Dt = 1.f / 60.f;
    FWindowTraffic Blocked;
    AddCar(Blocked, 0, 20, 1, 13, 13.8f);
    AddCar(Blocked, 2, 48, 1, 8, 8, 100);
    AddCar(Blocked, 4, 20, 0, 8, 8, 100);
    AddCar(Blocked, 6, 48, 0, 8, 8, 100);
    for (int32 Frame = 0; Frame < 240; ++Frame)
    {
        Blocked.Tick(Dt, TEXT("clear"));
        if (!CheckTraffic(*this, Blocked, TEXT("Blocked passing lane"), Frame)) return false;
        if (!TestFalse(TEXT("A blocked passing lane keeps the follower in its lane"), Blocked.Cars[0].IsChangingLane())) return false;
    }
    TestTrue(TEXT("The fast follower brakes behind the slower leader"), Blocked.Cars[0].Speed < 10);
    TestTrue(TEXT("The follower never passes through its leader"), Blocked.Cars[0].Position < Blocked.Cars[1].Position);

    FWindowTraffic Passing;
    AddCar(Passing, 0, 20, 1, 11, 13.8f);
    AddCar(Passing, 2, 55, 1, 7, 7, 100);
    bool bChanged = false, bPassed = false, bReturned = false;
    double PreviousX = Passing.Location(Passing.Cars[0], 695).X;
    for (int32 Frame = 0; Frame < 60 * 40; ++Frame)
    {
        Passing.Tick(Dt, TEXT("clear"));
        if (!CheckTraffic(*this, Passing, TEXT("Unobstructed overtake"), Frame)) return false;
        const FWindowTrafficCar& Car = Passing.Cars[0];
        const double X = Passing.Location(Car, 695).X;
        if (!TestTrue(TEXT("Lane changes have continuous lateral movement"), FMath::Abs(X - PreviousX) < 10)) return false;
        PreviousX = X;
        bChanged |= Car.IsChangingLane();
        if (Car.IsChangingLane()
            && !TestTrue(TEXT("A changing car reserves both lanes"), Car.Occupies(0) && Car.Occupies(1))) return false;
        if (Frame == 119)
            TestTrue(TEXT("The 3.2-second change is still progressing after two seconds"), Car.IsChangingLane() && X > 220 && X < 520);
        if (Frame == 199)
            TestTrue(TEXT("The change finishes in the inner lane after 3.2 seconds"), Car.Lane == 0 && !Car.IsChangingLane());
        if (!bPassed && Passing.Gap(Car, Passing.Cars[1]) > FWindowTraffic::RoadLength * .5f)
        {
            bPassed = true;
            TestTrue(TEXT("The actual overtake takes place entirely in the inner lane"), Car.Lane == 0 && Car.TargetLane == 0);
        }
        bReturned |= bPassed && Car.Lane == 1 && !Car.IsChangingLane();
    }
    TestTrue(TEXT("An empty adjacent lane permits a lane change"), bChanged);
    TestTrue(TEXT("The faster vehicle actually overtakes"), bPassed);
    TestTrue(TEXT("After passing and leaving a safe gap, the car returns to the outer lane"), bReturned);

    FWindowTraffic DistantTraffic;
    AddCar(DistantTraffic, 0, 20, 1, 11, 13.8f);
    AddCar(DistantTraffic, 2, 55, 1, 7, 7, 100);
    AddCar(DistantTraffic, 4, 250, 0, 6, 6, 100);
    DistantTraffic.Tick(Dt, TEXT("clear"));
    TestTrue(TEXT("A slow car far ahead in the inner lane does not block a safe overtake"), DistantTraffic.Cars[0].IsChangingLane());

    FWindowTraffic RearApproach;
    AddCar(RearApproach, 0, 100, 1, 9, 13.8f);
    AddCar(RearApproach, 2, 124, 1, 7, 7, 100);
    AddCar(RearApproach, 4, 78, 0, 16, 16, 100);
    for (int32 Frame = 0; Frame < 15; ++Frame)
    {
        RearApproach.Tick(Dt, TEXT("clear"));
        if (!CheckTraffic(*this, RearApproach, TEXT("Fast rear approach"), Frame)) return false;
        if (!TestFalse(TEXT("A fast approaching car blocks an unsafe cut-in"), RearApproach.Cars[0].IsChangingLane())) return false;
    }

    FWindowTraffic Reservation;
    AddCar(Reservation, 0, 20, 1, 13.8f, 13.8f);
    AddCar(Reservation, 2, 38, 1, 9, 13.8f);
    AddCar(Reservation, 4, 65, 1, 7, 7, 100);
    Reservation.Tick(Dt, TEXT("clear"));
    const int32 ApplicantsChanging = int32(Reservation.Cars[0].IsChangingLane()) + int32(Reservation.Cars[1].IsChangingLane());
    TestEqual(TEXT("Two nearby applicants cannot reserve the same gap simultaneously"), ApplicantsChanging, 1);
    for (int32 Frame = 0; Frame < 360; ++Frame)
    {
        Reservation.Tick(Dt, TEXT("clear"));
        if (!CheckTraffic(*this, Reservation, TEXT("Simultaneous reservations"), Frame)) return false;
    }

    FWindowTraffic Seam;
    AddCar(Seam, 0, FWindowTraffic::RoadLength - 12, 1, 12, 13.8f, 100);
    AddCar(Seam, 2, 5, 1, 5, 5, 100);
    for (int32 Frame = 0; Frame < 300; ++Frame)
    {
        Seam.Tick(Dt, TEXT("clear"));
        if (!CheckTraffic(*this, Seam, TEXT("Following across loop seam"), Frame)) return false;
    }
    TestTrue(TEXT("Cars cross the loop seam while preserving their following gap"), Seam.Wraps > 0);

    FWindowTraffic ChangingAtSeam;
    AddCar(ChangingAtSeam, 0, FWindowTraffic::RoadLength - 2, 1, 10, 10);
    ChangingAtSeam.Cars[0].TargetLane = 0;
    ChangingAtSeam.Cars[0].ChangeTime = 1;
    for (int32 Frame = 0; Frame < 180; ++Frame) ChangingAtSeam.Tick(Dt, TEXT("clear"));
    TestEqual(TEXT("A lane change survives recycling without snapping back sideways"), ChangingAtSeam.Cars[0].Lane, 0);
    TestEqual(TEXT("Changing car crosses the seam exactly once"), ChangingAtSeam.Wraps, 1);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowTrafficStabilityTest, "OutOfWindow.City.TrafficStability",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWindowTrafficStabilityTest::RunTest(const FString& Parameters)
{
    FWindowTraffic Initial = CityTraffic();
    TestEqual(TEXT("All sixteen scene sedans are registered"), Initial.Cars.Num(), 16);
    Initial.Add(0, FVector(220, 1100, 695));
    TestEqual(TEXT("Actor rescans do not duplicate cars"), Initial.Cars.Num(), 16);
    for (int32 Id = 0; Id < Initial.Cars.Num(); ++Id)
    {
        const FWindowTrafficCar& Car = Initial.Cars[Id];
        TestEqual(TEXT("Discovery order does not affect simulation order"), Car.Id, Id);
        TestEqual(TEXT("Opposite carriageways retain their directions"), Car.Direction, Id % 2 ? 1 : -1);
        TestTrue(TEXT("Dry urban cruising targets are 34-50 km/h"), Car.DesiredSpeed >= 34.f / 3.6f && Car.DesiredSpeed <= 50.f / 3.6f);
        TestTrue(TEXT("Registration preserves the actor's longitudinal position"),
            FMath::IsNearlyEqual(Initial.Location(Car, 695).Y, double(1100 - ((Id * 1337) % 20400)), .01));
    }
    if (!CheckTraffic(*this, Initial, TEXT("Initial scene"), 0)) return false;

    FWindowTraffic InvalidTime = Initial;
    InvalidTime.Tick(0, TEXT("clear"));
    InvalidTime.Tick(-1, TEXT("clear"));
    InvalidTime.Tick(std::numeric_limits<float>::quiet_NaN(), TEXT("clear"));
    InvalidTime.Tick(std::numeric_limits<float>::infinity(), TEXT("clear"));
    for (int32 Index = 0; Index < Initial.Cars.Num(); ++Index)
    {
        TestEqual(TEXT("Invalid frame durations leave positions unchanged"), InvalidTime.Cars[Index].Position, Initial.Cars[Index].Position);
        TestEqual(TEXT("Invalid frame durations leave speeds unchanged"), InvalidTime.Cars[Index].Speed, Initial.Cars[Index].Speed);
    }
    FWindowTraffic ValidTime = Initial;
    ValidTime.Tick(1.f / 30.f, TEXT("clear"));
    InvalidTime.Tick(1.f / 30.f, TEXT("clear"));
    TestEqual(TEXT("Valid frames resume normally after invalid durations"), InvalidTime.Cars[0].Position, ValidTime.Cars[0].Position);

    const TCHAR* Weathers[] = { TEXT("clear"), TEXT("rain"), TEXT("snow"), TEXT("fog") };
    double MeanSpeeds[4] = {};
    for (int32 WeatherIndex = 0; WeatherIndex < 4; ++WeatherIndex)
    {
        FWindowTraffic Traffic = Initial;
        int32 PreviousOvertakes = 0;
        for (int32 Frame = 0; Frame < 30 * 600; ++Frame)
        {
            Traffic.Tick(1.f / 30.f, Weathers[WeatherIndex]);
            if (!CheckTraffic(*this, Traffic, Weathers[WeatherIndex], Frame)) return false;
            if (WeatherIndex == 0 && Traffic.OvertakeChanges > PreviousOvertakes && Traffic.OvertakeChanges <= 3)
                AddInfo(FString::Printf(TEXT("City overtake lane change %d completes at %.2f seconds"), Traffic.OvertakeChanges, (Frame + 1) / 30.f));
            PreviousOvertakes = Traffic.OvertakeChanges;
            if (Frame >= 30 * 540)
                for (const FWindowTrafficCar& Car : Traffic.Cars) MeanSpeeds[WeatherIndex] += Car.Speed / (30 * 60 * Traffic.Cars.Num());
        }
        TestTrue(TEXT("The ten-minute simulation recycles traffic at the loop boundary"), Traffic.Wraps > 0);
        TestTrue(TEXT("The minimum recorded gap remains safe between render frames"), Traffic.MinimumObservedGap >= FWindowTraffic::MinimumGap - .001f);
        AddInfo(FString::Printf(TEXT("%s 600s: changes=%d overtakes=%d wraps=%d minimumGap=%.3fm"),
            Weathers[WeatherIndex], Traffic.CompletedChanges, Traffic.OvertakeChanges, Traffic.Wraps, Traffic.MinimumObservedGap));
        if (WeatherIndex == 0) TestTrue(TEXT("The actual City layout permits overtaking when gaps open"), Traffic.OvertakeChanges > 0);
    }
    TestTrue(TEXT("Rain slows the same traffic stream"), MeanSpeeds[1] < MeanSpeeds[0]);
    TestTrue(TEXT("Snow and fog are more cautious than rain"), MeanSpeeds[2] < MeanSpeeds[1] && MeanSpeeds[3] < MeanSpeeds[1]);

    FWindowTraffic Hitches = Initial;
    for (int32 Frame = 0; Frame < 1200; ++Frame)
    {
        const float PreviousPosition = Hitches.Cars[0].Position;
        Hitches.Tick(Frame % 19 == 0 ? 5.f : 1.f / 144.f, Weathers[(Frame / 300) % 4]);
        if (!CheckTraffic(*this, Hitches, TEXT("Weather changes and suspend hitches"), Frame)) return false;
        const float Travel = FMath::Fmod(Hitches.Cars[0].Position - PreviousPosition + FWindowTraffic::RoadLength, FWindowTraffic::RoadLength);
        if (!TestTrue(TEXT("A multi-second render hitch never teleports a car"), Travel < 4.f)) return false;
    }

    FWindowTraffic ThirtyFps = Initial, OneTwentyFps = Initial;
    for (const TCHAR* Weather : Weathers)
    {
        for (int32 Frame = 0; Frame < 30 * 30; ++Frame) ThirtyFps.Tick(1.f / 30.f, Weather);
        for (int32 Frame = 0; Frame < 120 * 30; ++Frame) OneTwentyFps.Tick(1.f / 120.f, Weather);
        if (!CheckTraffic(*this, ThirtyFps, TEXT("30 fps after weather change"), 0)
            || !CheckTraffic(*this, OneTwentyFps, TEXT("120 fps after weather change"), 0)) return false;
        for (int32 Index = 0; Index < Initial.Cars.Num(); ++Index)
        {
            const FWindowTrafficCar& A = ThirtyFps.Cars[Index];
            const FWindowTrafficCar& B = OneTwentyFps.Cars[Index];
            TestTrue(TEXT("Render frame rate preserves longitudinal position"), FMath::IsNearlyEqual(A.Position, B.Position, .001f));
            TestTrue(TEXT("Render frame rate preserves speed"), FMath::IsNearlyEqual(A.Speed, B.Speed, .0001f));
            TestTrue(TEXT("Render frame rate preserves lane-change timing"), FMath::IsNearlyEqual(A.ChangeTime, B.ChangeTime, .0001f));
            TestEqual(TEXT("Render frame rate preserves occupied lane"), A.Lane, B.Lane);
            TestEqual(TEXT("Render frame rate preserves lane-change decisions"), A.TargetLane, B.TargetLane);
        }
        TestEqual(TEXT("Render frame rate preserves completed manoeuvres"), ThirtyFps.CompletedChanges, OneTwentyFps.CompletedChanges);
        TestEqual(TEXT("Render frame rate preserves recycling"), ThirtyFps.Wraps, OneTwentyFps.Wraps);
    }
    return true;
}

#endif
