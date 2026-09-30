#include "WindowPrecipitation.h"

#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"

AWindowPrecipitation::AWindowPrecipitation()
{
    PrimaryActorTick.bCanEverTick = true;
    RainSource = FSoftObjectPath(TEXT("/Game/Weather/M_Rain.M_Rain"));
    SnowSource = FSoftObjectPath(TEXT("/Game/Weather/M_Snow.M_Snow"));
    SplashSource = FSoftObjectPath(TEXT("/Game/Weather/M_RainSplash.M_RainSplash"));
    PlaneSource = FSoftObjectPath(TEXT("/Engine/BasicShapes/Plane.Plane"));
    Rain = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Rain"));
    SetRootComponent(Rain);
    Snow = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Snow"));
    Snow->SetupAttachment(Rain);
    Splashes = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("RainSplashes"));
    Splashes->SetupAttachment(Rain);
    for (UInstancedStaticMeshComponent* Component : {Rain.Get(), Snow.Get(), Splashes.Get()})
    {
        Component->SetMobility(EComponentMobility::Movable);
        Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Component->SetCastShadow(false);
        Component->SetReceivesDecals(false);
        Component->SetVisibleInRayTracing(false);
        Component->bAffectDistanceFieldLighting = false;
        Component->bAffectDynamicIndirectLighting = false;
        Component->SetNumCustomDataFloats(4);
        // WPO stays inside the precipitation volume, including edge wrapping.
        Component->SetBoundsScale(2.0f);
        Component->SetVisibility(false);
    }
    Splashes->SetNumCustomDataFloats(7);
}

void AWindowPrecipitation::BeginPlay()
{
    Super::BeginPlay();
    UStaticMesh* Plane = PlaneSource.LoadSynchronous();
    Rain->SetStaticMesh(Plane);
    Snow->SetStaticMesh(Plane);
    Splashes->SetStaticMesh(Plane);
    if (UMaterialInterface* Material = RainSource.LoadSynchronous())
    {
        RainMaterial = UMaterialInstanceDynamic::Create(Material, this);
        Rain->SetMaterial(0, RainMaterial);
    }
    if (UMaterialInterface* Material = SnowSource.LoadSynchronous())
    {
        SnowMaterial = UMaterialInstanceDynamic::Create(Material, this);
        Snow->SetMaterial(0, SnowMaterial);
    }
    if (UMaterialInterface* Material = SplashSource.LoadSynchronous())
    {
        SplashMaterial = UMaterialInstanceDynamic::Create(Material, this);
        Splashes->SetMaterial(0, SplashMaterial);
    }
    for (UMaterialInstanceDynamic* Material : {RainMaterial.Get(), SnowMaterial.Get()})
    {
        if (!Material) continue;
        Material->SetVectorParameterValue(TEXT("VolumeMin"), FLinearColor(VolumeMin));
        Material->SetVectorParameterValue(TEXT("VolumeSize"), FLinearColor(VolumeSize));
    }
    if (!Plane || !RainMaterial || !SnowMaterial || !SplashMaterial)
        UE_LOG(LogTemp, Warning, TEXT("OutOfWindow precipitation assets missing; run build_precipitation.py."));
}

void AWindowPrecipitation::SetView(const FVector& CameraLocation, const FVector& CameraForward)
{
    FVector Forward = FVector(CameraForward.X, CameraForward.Y, 0).GetSafeNormal();
    if (Forward.IsNearlyZero()) Forward = FVector::ForwardVector;
    const FVector Centre = CameraLocation + Forward * 2000.0;
    VolumeMin = FVector(Centre.X - VolumeSize.X * 0.5, Centre.Y - VolumeSize.Y * 0.5,
                        CameraLocation.Z - 3000.0);
    WindOffset = FVector::ZeroVector;
    CreateParticles(Rain, 3200, false, Forward);
    CreateParticles(Snow, 1800, true, Forward);
    CreateSplashes(CameraLocation, CameraForward);
    for (UMaterialInstanceDynamic* Material : {RainMaterial.Get(), SnowMaterial.Get()})
    {
        if (!Material) continue;
        Material->SetVectorParameterValue(TEXT("VolumeMin"), FLinearColor(VolumeMin));
        Material->SetVectorParameterValue(TEXT("VolumeSize"), FLinearColor(VolumeSize));
        Material->SetVectorParameterValue(TEXT("WindOffset"), FLinearColor::Black);
    }
}

void AWindowPrecipitation::CreateSplashes(const FVector& CameraLocation, const FVector& CameraForward)
{
    Splashes->ClearInstances();
    if (!GetWorld()) return;
    FVector Forward = FVector(CameraForward.X, CameraForward.Y, 0).GetSafeNormal();
    if (Forward.IsNearlyZero()) Forward = FVector::ForwardVector;
    const FVector Right = FVector::CrossProduct(FVector::UpVector, Forward).GetSafeNormal();
    const FQuat Rotation = FRotationMatrix::MakeFromXZ(Right, Forward).ToQuat();
    FRandomStream Random(42375);
    FCollisionQueryParams Query(SCENE_QUERY_STAT(OOWRainSplashSurface), true, this);
    const FCollisionObjectQueryParams Objects(FCollisionObjectQueryParams::AllObjects);
    int32 SurfaceCount = 0;
    Splashes->PreAllocateInstancesMemory(768 * 3);
    for (int32 Sample = 0; Sample < 768; ++Sample)
    {
        const float Distance = Random.FRandRange(1500.0f, 8000.0f);
        FVector Start = CameraLocation + Forward * Distance
            + Right * Random.FRandRange(-0.8f, 0.8f) * Distance;
        Start.Z = CameraLocation.Z + 25000.0;
        FVector End = Start;
        End.Z = CameraLocation.Z - 50000.0;
        FHitResult Hit;
        // Complex collision keeps impacts on actual mesh triangles. Never use
        // a bounding-box top as a fallback: sloped/concave ground would float.
        if (!GetWorld()->LineTraceSingleByObjectType(Hit, Start, End, Objects, Query)
            || !Hit.GetComponent() || Hit.GetComponent()->GetMobility() != EComponentMobility::Static
            || Hit.ImpactNormal.Z < 0.72
            || FVector::DotProduct((Hit.ImpactPoint - CameraLocation).GetSafeNormal(),
                                    CameraForward.GetSafeNormal()) < 0.65)
            continue;
        const FVector Normal = Hit.ImpactNormal.GetSafeNormal();
        const FVector Centre = Hit.ImpactPoint + Normal * 1.0;
        const float Phase = Random.FRand();
        const float Rank = Random.FRand();
        const float Angle = Random.FRandRange(0.0f, 2.0f * PI);
        for (int32 Droplet = 0; Droplet < 3; ++Droplet)
        {
            const FVector Scale(Random.FRandRange(0.009f, 0.018f),
                                Random.FRandRange(0.018f, 0.032f), 1.0);
            const int32 Instance = Splashes->AddInstance(FTransform(Rotation, Centre, Scale), true);
            float Data[] = {static_cast<float>(Normal.X), static_cast<float>(Normal.Y),
                static_cast<float>(Normal.Z), Phase, Angle + Droplet * (2.0f * PI / 3.0f),
                Rank, Random.FRandRange(100.0f, 180.0f)};
            Splashes->SetCustomData(Instance, MakeArrayView(Data, 7), false);
        }
        ++SurfaceCount;
    }
    Splashes->MarkRenderStateDirty();
    UE_LOG(LogTemp, Display, TEXT("OOW_SPLASH_SURFACES %d; droplets=%d; complex collision, one-time sampling"),
           SurfaceCount, Splashes->GetInstanceCount());
    if (SurfaceCount == 0)
        UE_LOG(LogTemp, Warning, TEXT("No rain-splash surface hits; verify imported mesh complex collision."));
}

void AWindowPrecipitation::CreateParticles(UInstancedStaticMeshComponent* Component, int32 Count,
                                         bool bSnow, const FVector& CameraForward)
{
    Component->ClearInstances();
    Component->PreAllocateInstancesMemory(Count);
    FRandomStream Random(bSnow ? 64123 : 12341);
    const FVector Right = FVector::CrossProduct(FVector::UpVector, CameraForward).GetSafeNormal();
    const FQuat Rotation = FRotationMatrix::MakeFromXZ(Right, CameraForward).ToQuat();
    for (int32 Index = 0; Index < Count; ++Index)
    {
        const FVector Centre = VolumeMin + FVector(Random.FRand() * VolumeSize.X,
            Random.FRand() * VolumeSize.Y, Random.FRand() * VolumeSize.Z);
        const float Size = Random.FRandRange(0.025f, 0.065f);
        // Sub-centimetre streaks alias away at window distance; rain drops are
        // seen as 1-2 cm refractive filaments, not hairlines.
        const FVector Scale = bSnow ? FVector(Size, Size, Size)
            : FVector(Random.FRandRange(0.010f, 0.020f), Random.FRandRange(0.3f, 0.6f), 1.0);
        const int32 Instance = Component->AddInstance(FTransform(Rotation, Centre, Scale), true);
        float Data[] = {static_cast<float>(Centre.X), static_cast<float>(Centre.Y),
                              static_cast<float>(Centre.Z), Random.FRand()};
        Component->SetCustomData(Instance, MakeArrayView(Data, 4), false);
    }
    Component->MarkRenderStateDirty();
}

void AWindowPrecipitation::SetWeather(float InRain, float InSnow, const FVector& WindVelocity)
{
    TargetRain = FMath::Clamp(InRain, 0.0f, 1.0f);
    TargetSnow = FMath::Clamp(InSnow, 0.0f, 1.0f);
    TargetWind = FVector(WindVelocity.X, WindVelocity.Y, 0).GetClampedToMaxSize(3000.0);
}

void AWindowPrecipitation::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    const float Dt = FMath::Min(DeltaSeconds, 0.1f);
    RainAmount = FMath::FInterpTo(RainAmount, TargetRain, Dt, 1.5f);
    SnowAmount = FMath::FInterpTo(SnowAmount, TargetSnow, Dt, 1.5f);
    Wind = FMath::VInterpTo(Wind, TargetWind, Dt, 1.5f);
    WindOffset += Wind * Dt;
    WindOffset.X = FMath::Fmod(WindOffset.X, VolumeSize.X);
    WindOffset.Y = FMath::Fmod(WindOffset.Y, VolumeSize.Y);
    Rain->SetVisibility(RainMaterial && RainAmount > 0.002f);
    Snow->SetVisibility(SnowMaterial && SnowAmount > 0.002f);
    Splashes->SetVisibility(SplashMaterial && RainAmount > 0.002f);
    if (RainMaterial)
    {
        RainMaterial->SetScalarParameterValue(TEXT("Amount"), RainAmount);
        RainMaterial->SetVectorParameterValue(TEXT("WindOffset"), FLinearColor(WindOffset));
        RainMaterial->SetVectorParameterValue(TEXT("WindVelocity"), FLinearColor(Wind));
    }
    if (SnowMaterial)
    {
        SnowMaterial->SetScalarParameterValue(TEXT("Amount"), SnowAmount);
        SnowMaterial->SetVectorParameterValue(TEXT("WindOffset"), FLinearColor(WindOffset));
    }
    if (SplashMaterial)
    {
        SplashMaterial->SetScalarParameterValue(TEXT("OOW_RainAmount"), RainAmount);
        SplashMaterial->SetVectorParameterValue(TEXT("WindVelocity"), FLinearColor(Wind));
    }
}
