#if WITH_DEV_AUTOMATION_TESTS

#include "../WindowTraffic.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowTrafficHeadlightMountingTest, "OutOfWindow.City.TrafficHeadlightMounting",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWindowTrafficHeadlightMountingTest::RunTest(const FString& Parameters)
{
    FWindowTraffic Traffic;
    Traffic.Add(0, FVector(220, -10000, 695));
    Traffic.Add(1, FVector(-220, -10000, 735));
    TestEqual(TEXT("Add retains the first car's ground height"), Traffic.Cars[0].GroundZ, 695.f);
    TestEqual(TEXT("Add retains the opposite car's ground height"), Traffic.Cars[1].GroundZ, 735.f);
    const FVector Camera(0, -10000, 800);
    const auto Straight = Traffic.HeadlightTargets(Camera, 1.f);
    if (!TestEqual(TEXT("Both nearby carriageways receive a headlight"), Straight.Num(), 2)) return false;
    for (const FWindowTrafficHeadlight& Light : Straight)
    {
        const FWindowTrafficCar* Car = Traffic.Cars.FindByPredicate([&](const FWindowTrafficCar& Item) { return Item.Id == Light.CarId; });
        if (!TestNotNull(TEXT("A light identifies an existing car"), Car)) return false;
        const FVector Offset = Light.Location - Traffic.Location(*Car, Car->GroundZ);
        const FVector Forward = Light.Rotation.Vector(); // A spot light emits along its local +X axis.
        TestTrue(TEXT("Straight mounting has no sideways drift"), FMath::Abs(Offset.X) < .01);
        TestTrue(TEXT("Mount sits 216 cm ahead in either travel direction"), FMath::IsNearlyEqual(Offset.Y * Car->Direction, 216., .01));
        TestTrue(TEXT("Mount sits 67 cm above the preserved ground height"), FMath::IsNearlyEqual(Offset.Z, 67., .01));
        TestTrue(TEXT("Spot forward axis follows traffic, not the opposite lane"), Forward.Y * Car->Direction > .99);
        TestTrue(TEXT("Spot points down toward the road"), Forward.Z < -.10 && Forward.Z > -.11);
        TestTrue(TEXT("Near cars receive full night strength"), FMath::IsNearlyEqual(Light.Strength, 1.f, .001f));
    }

    for (FWindowTrafficCar& Car : Traffic.Cars)
    {
        Car.Lane = 0;
        Car.TargetLane = 1;
        Car.ChangeTime = FWindowTraffic::ChangeDuration * .5f;
        Car.Speed = 10.f;
    }
    const auto Turning = Traffic.HeadlightTargets(Camera, 1.f);
    if (!TestEqual(TEXT("Lane-changing cars keep their lights"), Turning.Num(), 2)) return false;
    for (const FWindowTrafficHeadlight& Light : Turning)
    {
        const FWindowTrafficCar* Car = Traffic.Cars.FindByPredicate([&](const FWindowTrafficCar& Item) { return Item.Id == Light.CarId; });
        if (!TestNotNull(TEXT("A turning light identifies an existing car"), Car)) return false;
        const FVector Offset = Light.Location - Traffic.Location(*Car, Car->GroundZ);
        // Compare with the actual trajectory around this instant instead of
        // reproducing the implementation's yaw or quaternion expression.
        FWindowTrafficCar Before = *Car, After = *Car;
        constexpr float SampleTime = .005f;
        Before.Position -= Car->Speed * SampleTime;
        Before.ChangeTime -= SampleTime;
        After.Position += Car->Speed * SampleTime;
        After.ChangeTime += SampleTime;
        const FVector Travel = (Traffic.Location(After, After.GroundZ) - Traffic.Location(Before, Before.GroundZ)).GetSafeNormal2D();
        TestTrue(TEXT("Mount follows the car's real lane-change trajectory"), FVector::DotProduct(Offset.GetSafeNormal2D(), Travel) > .9999);
        TestTrue(TEXT("Spot follows that trajectory independently of its local axis"), FVector::DotProduct(Light.Rotation.Vector().GetSafeNormal2D(), Travel) > .9999);
        TestTrue(TEXT("Front offset length stays 216 cm through the turn"), FMath::IsNearlyEqual(Offset.Size2D(), 216., .01));
        TestTrue(TEXT("The headlight turns into the outer lane on both carriageways"), Offset.X * Car->Direction < -1.);
        TestTrue(TEXT("Turning preserves mounting height"), FMath::IsNearlyEqual(Offset.Z, 67., .01));
        TestTrue(TEXT("Turning preserves the downward beam"), Light.Rotation.Vector().Z < -.10 && Light.Rotation.Vector().Z > -.11);
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowTrafficHeadlightBudgetTest, "OutOfWindow.City.TrafficHeadlightBudgetAndFade",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWindowTrafficHeadlightBudgetTest::RunTest(const FString& Parameters)
{
    FWindowTraffic Traffic;
    Traffic.Add(0, FVector(220, -10000, 695));
    const FVector Position = Traffic.Location(Traffic.Cars[0], Traffic.Cars[0].GroundZ);
    TestEqual(TEXT("Daytime has no active headlights"), Traffic.HeadlightTargets(Position, 0.f).Num(), 0);
    TestEqual(TEXT("The night threshold itself has no active headlights"), Traffic.HeadlightTargets(Position, .58f).Num(), 0);
    const auto Twilight = Traffic.HeadlightTargets(Position, .72f);
    const auto FullNight = Traffic.HeadlightTargets(Position, .86f);
    if (!TestEqual(TEXT("Twilight activates the nearby car"), Twilight.Num(), 1)
        || !TestEqual(TEXT("Full night activates the nearby car"), FullNight.Num(), 1)) return false;
    TestTrue(TEXT("Twilight fades in instead of switching straight to full strength"), Twilight[0].Strength > 0.f && Twilight[0].Strength < 1.f);
    TestTrue(TEXT("Night reaches full strength by 0.86"), FMath::IsNearlyEqual(FullNight[0].Strength, 1.f, .001f));

    float Previous = 2.f;
    for (const float Distance : {6000.f, 8000.f, 12000.f, 15000.f})
    {
        // Vertical separation ensures the range test uses three dimensions.
        const auto Lights = Traffic.HeadlightTargets(Position + FVector(0, 0, Distance), 1.f);
        if (!TestEqual(TEXT("A car within the fade range remains active"), Lights.Num(), 1)) return false;
        TestTrue(TEXT("Distance strength stays positive and decreases monotonically"), Lights[0].Strength > 0.f && Lights[0].Strength < Previous);
        if (Distance == 6000.f) TestTrue(TEXT("A car inside 65 m has full strength"), FMath::IsNearlyEqual(Lights[0].Strength, 1.f, .001f));
        Previous = Lights[0].Strength;
    }
    TestEqual(TEXT("A car beyond 160 m is removed"), Traffic.HeadlightTargets(Position + FVector(0, 0, 16500), 1.f).Num(), 0);

    FWindowTraffic Crowded;
    for (int32 Id = 11; Id >= 0; --Id)
        // Separation exceeds the opposing 216 cm front offsets, so distance
        // ordering is unambiguous for either car centres or lamp mounts.
        Crowded.Add(Id, FVector(Id % 2 ? -220 : 220, -10000 - Id * 1000, Id == 0 ? 30000 : 695));
    Crowded.Add(12, FVector(220, -30000, 695));
    const auto Selected = Crowded.HeadlightTargets(FVector(0, -10000, 695), 1.f);
    TestEqual(TEXT("The runtime budget is eight lights"), FWindowTraffic::MaxHeadlights, 8);
    if (!TestEqual(TEXT("Crowded traffic respects the light budget"), Selected.Num(), FWindowTraffic::MaxHeadlights)) return false;
    TSet<int32> Ids;
    for (const FWindowTrafficHeadlight& Light : Selected)
    {
        TestFalse(TEXT("No car receives duplicate target entries"), Ids.Contains(Light.CarId));
        Ids.Add(Light.CarId);
        TestTrue(TEXT("Only the nearest eight cars are chosen in 3D"), Light.CarId >= 1 && Light.CarId <= 8);
    }
    for (int32 Id = 1; Id <= 8; ++Id) TestTrue(TEXT("Every nearest car is represented"), Ids.Contains(Id));
    TestFalse(TEXT("A car directly above the camera is excluded by its 3D distance"), Ids.Contains(0));
    TestFalse(TEXT("A distant road car cannot consume the budget"), Ids.Contains(12));
    return true;
}

#endif
