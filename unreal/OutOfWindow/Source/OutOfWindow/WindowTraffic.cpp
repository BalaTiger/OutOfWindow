#include "WindowTraffic.h"

#include "Components/SpotLightComponent.h"
#include "Engine/Scene.h"
#include "GameFramework/Actor.h"
#include "HAL/IConsoleManager.h"

namespace
{
TAutoConsoleVariable<float> HeadlightLumens(TEXT("oow.HeadlightLumens"), 450.f,
    TEXT("Combined road illumination from each sedan's pair of dipped headlights, in lumens."));
}

void FWindowTraffic::Add(int32 Id, const FVector& Origin)
{
    if (Cars.ContainsByPredicate([Id](const FWindowTrafficCar& Car) { return Car.Id == Id; })) return;
    FWindowTrafficCar Car;
    Car.Id = Id;
    Car.GroundZ = Origin.Z;
    Car.Direction = Id % 2 ? 1 : -1;
    Car.Lane = Car.TargetLane = FMath::Abs(Origin.X) > 350 ? 1 : 0;
    Car.Position = Car.Direction < 0 ? (NearY - Origin.Y) / 100 : (Origin.Y - FarY) / 100;
    Car.Position = FMath::Fmod(Car.Position + RoadLength, RoadLength);
    Car.DesiredSpeed = (34.f + FMath::Frac(Id * .618034f) * 16.f) / 3.6f;
    Car.Speed = Car.DesiredSpeed;
    Car.Cooldown = 1.f + Id * .17f;
    Cars.Add(Car);
    Cars.Sort([](const FWindowTrafficCar& A, const FWindowTrafficCar& B) { return A.Id < B.Id; });
}

float FWindowTraffic::Gap(const FWindowTrafficCar& Car, const FWindowTrafficCar& Other) const
{
    return FMath::Fmod(Other.Position - Car.Position + RoadLength, RoadLength) - CarLength;
}

const FWindowTrafficCar* FWindowTraffic::Leader(const FWindowTrafficCar& Car, int32 Lane) const
{
    const FWindowTrafficCar* Result = nullptr;
    float Nearest = RoadLength;
    // ponytail: scan the 16 cars directly; use lane-sorted neighbours if this becomes a large traffic network.
    for (const FWindowTrafficCar& Other : Cars)
    {
        if (Other.Id == Car.Id || Other.Direction != Car.Direction || !Other.Occupies(Lane)) continue;
        const float Distance = Gap(Car, Other);
        if (Distance < Nearest) { Nearest = Distance; Result = &Other; }
    }
    return Result;
}

bool FWindowTraffic::CanChange(const FWindowTrafficCar& Car, int32 Lane, float Headway) const
{
    for (const FWindowTrafficCar& Other : Cars)
    {
        if (Other.Id == Car.Id || Other.Direction != Car.Direction || !Other.Occupies(Lane)) continue;
        const float Ahead = Gap(Car, Other);
        const float Behind = Gap(Other, Car);
        // Reserve both lanes for the whole manoeuvre, including the closing distance
        // of a faster car behind. A second decision in this step sees the reservation.
        if (Ahead < MinimumGap + Car.Speed * Headway + FMath::Max(0.f, Car.Speed - Other.Speed) * ChangeDuration
            || Behind < MinimumGap + Other.Speed * Headway + FMath::Max(0.f, Other.Speed - Car.Speed) * ChangeDuration)
            return false;
    }
    return true;
}

void FWindowTraffic::Step(float Dt, float SpeedScale, float Headway)
{
    for (FWindowTrafficCar& Car : Cars)
    {
        Car.Cooldown = FMath::Max(0.f, Car.Cooldown - Dt);
        if (Car.IsChangingLane() || Car.Cooldown > 0 || Car.Speed < 3.f) continue;
        const FWindowTrafficCar* Front = Leader(Car, Car.Lane);
        const int32 NextLane = 1 - Car.Lane;
        const FWindowTrafficCar* NextFront = Leader(Car, NextLane);
        const float Desired = Car.DesiredSpeed * SpeedScale;
        const bool bBlocked = Front && Gap(Car, *Front) < FMath::Max(30.f, Car.Speed * 4.f)
            && Desired > Front->Speed + 1.f;
        const bool bFasterLane = !NextFront || Gap(Car, *NextFront) > FMath::Max(
            (Front ? Gap(Car, *Front) : 0.f) + 12.f,
            Car.Speed * 5.f + FMath::Max(0.f, Desired - NextFront->Speed) * ChangeDuration);
        // Pass on the inner lane; return only when the outer lane has enough room
        // to cruise, not while still alongside the vehicle just passed.
        const bool bReturn = Car.Lane == 0 && (!NextFront || Gap(Car, *NextFront)
            > Car.Speed * 6.f + FMath::Max(0.f, Desired - NextFront->Speed) * 10.f);
        if (((Car.Lane == 1 && bBlocked && bFasterLane) || bReturn) && CanChange(Car, NextLane, Headway))
        {
            Car.TargetLane = NextLane;
            Car.ChangeTime = 0;
        }
    }

    TArray<float, TInlineAllocator<32>> Speeds, Advances;
    for (const FWindowTrafficCar& Car : Cars)
    {
        const float Desired = FMath::Max(1.f, Car.DesiredSpeed * SpeedScale);
        const float Ratio = Car.Speed / Desired;
        float Acceleration = 1.6f * (1.f - FMath::Square(FMath::Square(Ratio)));
        float Available = RoadLength;
        for (int32 Lane = 0; Lane < 2; ++Lane)
        {
            if (!Car.Occupies(Lane)) continue;
            if (const FWindowTrafficCar* Front = Leader(Car, Lane))
            {
                const float Distance = Gap(Car, *Front);
                const float DesiredGap = MinimumGap + FMath::Max(0.f, Car.Speed * Headway
                    + Car.Speed * (Car.Speed - Front->Speed) / (2.f * FMath::Sqrt(1.6f * 2.4f)));
                Acceleration = FMath::Min(Acceleration, 1.6f * (1.f - FMath::Square(FMath::Square(Ratio))
                    - FMath::Square(DesiredGap / FMath::Max(.1f, Distance))));
                Available = FMath::Min(Available, FMath::Max(0.f, Distance - MinimumGap));
            }
        }
        float Speed = FMath::Max(0.f, Car.Speed + FMath::Clamp(Acceleration, -4.f, 1.6f) * Dt);
        float Advance = (Car.Speed + Speed) * .5f * Dt;
        // Collision guard also covers abrupt weather changes, stopped queues and the loop seam.
        if (Advance > Available) { Advance = Available; Speed = FMath::Min(Speed, Advance / Dt); }
        Speeds.Add(Speed);
        Advances.Add(Advance);
    }
    for (int32 Index = 0; Index < Cars.Num(); ++Index)
    {
        FWindowTrafficCar& Car = Cars[Index];
        Car.Speed = Speeds[Index];
        Car.Position += Advances[Index];
        if (Car.Position >= RoadLength) { Car.Position -= RoadLength; ++Wraps; }
        if (Car.IsChangingLane())
        {
            Car.ChangeTime += Dt * FMath::Min(1.f, Car.Speed / 3.f);
            if (Car.ChangeTime >= ChangeDuration)
            {
                if (Car.TargetLane == 0) ++OvertakeChanges;
                Car.Lane = Car.TargetLane;
                Car.ChangeTime = 0;
                Car.Cooldown = 8.f + FMath::Frac(Car.Id * .381966f) * 4.f;
                ++CompletedChanges;
            }
        }
    }
    for (const FWindowTrafficCar& Car : Cars)
        for (int32 Lane = 0; Lane < 2; ++Lane)
            if (Car.Occupies(Lane))
                if (const FWindowTrafficCar* Front = Leader(Car, Lane))
                    MinimumObservedGap = FMath::Min(MinimumObservedGap, Gap(Car, *Front));
}

void FWindowTraffic::Tick(float DeltaSeconds, const FString& Weather)
{
    if (!FMath::IsFinite(DeltaSeconds) || DeltaSeconds <= 0 || Cars.IsEmpty()) return;
    const bool bPoorVisibility = Weather == TEXT("snow") || Weather == TEXT("fog");
    const float Scale = bPoorVisibility ? .65f : Weather == TEXT("rain") ? .82f : 1.f;
    const float Headway = bPoorVisibility ? 2.3f : Weather == TEXT("rain") ? 1.9f : 1.4f;
    // Fixed substeps keep braking and reservations stable at different render rates.
    // Discard long suspend/loading hitches rather than teleporting through seconds of traffic.
    constexpr double StepSeconds = 1.0 / 60.0;
    Accumulator += FMath::Min(DeltaSeconds, .25f);
    while (Accumulator + 1.e-9 >= StepSeconds)
    {
        Step(static_cast<float>(StepSeconds), Scale, Headway);
        Accumulator -= StepSeconds;
    }
}

FVector FWindowTraffic::Location(const FWindowTrafficCar& Car, float Z) const
{
    const float T = FMath::Clamp(Car.ChangeTime / ChangeDuration, 0.f, 1.f);
    const float Blend = T * T * T * (10.f + T * (-15.f + 6.f * T));
    const float Lane = FMath::Lerp(static_cast<float>(Car.Lane), static_cast<float>(Car.TargetLane), Blend);
    return FVector(-Car.Direction * (220.f + Lane * 300.f),
        (Car.Direction < 0 ? NearY : FarY) + Car.Direction * Car.Position * 100.f, Z);
}

float FWindowTraffic::Yaw(const FWindowTrafficCar& Car) const
{
    const float T = FMath::Clamp(Car.ChangeTime / ChangeDuration, 0.f, 1.f);
    const float LateralSpeed = -Car.Direction * (Car.TargetLane - Car.Lane) * 3.f
        * 30.f * FMath::Square(T * (1.f - T)) / ChangeDuration * FMath::Min(1.f, Car.Speed / 3.f);
    return FMath::RadiansToDegrees(FMath::Atan2(-LateralSpeed, Car.Direction * FMath::Max(.1f, Car.Speed)));
}

TArray<FWindowTrafficHeadlight> FWindowTraffic::HeadlightTargets(const FVector& CameraLocation, float Night) const
{
    TArray<FWindowTrafficHeadlight> Targets;
    if (!FMath::IsFinite(Night) || CameraLocation.ContainsNaN()) return Targets;
    const float NightFade = FMath::SmoothStep(.58f, .86f, FMath::Clamp(Night, 0.f, 1.f));
    if (NightFade <= 0) return Targets;
    Targets.Reserve(Cars.Num());
    for (const FWindowTrafficCar& Car : Cars)
    {
        const FRotator BodyRotation(0, Yaw(Car), 0);
        FWindowTrafficHeadlight Target;
        Target.CarId = Car.Id;
        // Authored sedan front is local +Y; the two lenses are at +213 cm / 67 cm high.
        // One source just outside their shared front plane represents both lenses.
        Target.Location = Location(Car, Car.GroundZ) + BodyRotation.RotateVector(FVector(0, 216, 67));
        Target.Rotation = BodyRotation.RotateVector(FVector::RightVector).Rotation();
        Target.Rotation.Pitch = -6.f; // USpotLightComponent shines along its local +X.
        const float Distance = FVector::Distance(Target.Location, CameraLocation);
        Target.Strength = NightFade * (1.f - FMath::SmoothStep(6500.f, 16000.f, Distance));
        if (Target.Strength > .002f) Targets.Add(Target);
    }
    Targets.Sort([&CameraLocation](const FWindowTrafficHeadlight& A, const FWindowTrafficHeadlight& B)
    {
        const double ADistance = FVector::DistSquared(A.Location, CameraLocation);
        const double BDistance = FVector::DistSquared(B.Location, CameraLocation);
        return ADistance == BDistance ? A.CarId < B.CarId : ADistance < BDistance;
    });
    Targets.SetNum(FMath::Min(Targets.Num(), MaxHeadlights));
    return Targets;
}

void FWindowTraffic::UpdateHeadlights(AActor* Owner, const FVector& CameraLocation, float Night, float DeltaSeconds)
{
    ActiveHeadlights = 0;
    if (!IsValid(Owner) || !Owner->GetWorld()) return;
    const TArray<FWindowTrafficHeadlight> Targets = HeadlightTargets(CameraLocation, Night);
    // Retain a car's light slot through overtakes; only the farthest rejected
    // candidates relinquish slots. Distance fading makes that boundary subdued.
    for (FHeadlamp& Lamp : Headlamps)
    {
        if (Targets.ContainsByPredicate([&Lamp](const FWindowTrafficHeadlight& Target) { return Target.CarId == Lamp.CarId; })) continue;
        Lamp.CarId = INDEX_NONE;
        Lamp.Strength = 0;
        if (USpotLightComponent* Light = Lamp.Light.Get()) { Light->SetIntensity(0); Light->SetVisibility(false); }
    }
    const float Dt = FMath::IsFinite(DeltaSeconds) ? FMath::Clamp(DeltaSeconds, 0.f, .1f) : 0;
    const float Blend = 1.f - FMath::Exp(-5.f * Dt);
    const float Lumens = FMath::Clamp(HeadlightLumens.GetValueOnGameThread(), 0.f, 10000.f);
    for (const FWindowTrafficHeadlight& Target : Targets)
    {
        FHeadlamp* Lamp = Headlamps.FindByPredicate([&Target](const FHeadlamp& Entry) { return Entry.CarId == Target.CarId; });
        if (!Lamp) Lamp = Headlamps.FindByPredicate([](const FHeadlamp& Entry) { return Entry.CarId == INDEX_NONE; });
        if (!Lamp)
        {
            check(Headlamps.Num() < MaxHeadlights);
            Lamp = &Headlamps.AddDefaulted_GetRef();
        }
        USpotLightComponent* Light = Lamp->Light.Get();
        if (!Light)
        {
            Light = NewObject<USpotLightComponent>(Owner, NAME_None, RF_Transient);
            Light->SetMobility(EComponentMobility::Movable);
            Light->SetCastShadows(false);
            Light->SetIntensityUnits(ELightUnits::Lumens);
            Light->SetUseInverseSquaredFalloff(true);
            Light->SetUseTemperature(true);
            Light->SetTemperature(4500.f);
            Light->SetInnerConeAngle(14.f);
            Light->SetOuterConeAngle(22.f);
            Light->SetAttenuationRadius(3000.f);
            Light->SetSourceRadius(4.f);
            Light->SetIndirectLightingIntensity(0);
            Light->SetVolumetricScatteringIntensity(0);
            Light->SetAffectTranslucentLighting(false);
            Light->SetIntensity(0);
            Light->SetVisibility(false);
            Light->ComponentTags.Add(TEXT("OOWTrafficHeadlight"));
            Owner->AddInstanceComponent(Light);
            Light->RegisterComponent();
            Lamp->Light = Light;
        }
        Lamp->CarId = Target.CarId;
        Lamp->Strength = FMath::Lerp(Lamp->Strength, Target.Strength, Blend);
        Light->SetWorldLocationAndRotation(Target.Location, Target.Rotation);
        Light->SetIntensity(Lumens * Lamp->Strength);
        const bool bActive = Lumens * Lamp->Strength > .1f;
        Light->SetVisibility(bActive);
        ActiveHeadlights += bActive;
    }
}
