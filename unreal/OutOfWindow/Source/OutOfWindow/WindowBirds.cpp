#include "WindowBirds.h"

#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "MeshDescription.h"
#include "MeshUVChannelInfo.h"
#include "Misc/CommandLine.h"
#include "PhysicsEngine/BodySetup.h"
#include "StaticMeshAttributes.h"

namespace
{
// Original low-poly geometry, in centimetres. Built only once per world; no
// skeletal animation, downloaded assets, or per-frame mesh uploads are needed.
UStaticMesh* MakeBirdMesh(UObject* Outer, UMaterialInterface* Material,
                          const TArray<FVector3f>& Points, const TArray<int32>& Indices)
{
    FMeshDescription Description;
    FStaticMeshAttributes Attributes(Description);
    Attributes.Register();
    Attributes.GetVertexInstanceUVs().SetNumChannels(1);
    const FPolygonGroupID Group = Description.CreatePolygonGroup();
    Attributes.GetPolygonGroupMaterialSlotNames()[Group] = TEXT("Bird");
    for (int32 Index = 0; Index < Indices.Num(); Index += 3)
    {
        const FVector3f A = Points[Indices[Index]];
        const FVector3f B = Points[Indices[Index + 1]];
        const FVector3f C = Points[Indices[Index + 2]];
        const FVector3f Normal = FVector3f::CrossProduct(B - A, C - A).GetSafeNormal();
        const FVector3f Tangent = (B - A).GetSafeNormal();
        TArray<FVertexInstanceID> Corners;
        for (int32 Corner = 0; Corner < 3; ++Corner)
        {
            const FVertexID Vertex = Description.CreateVertex();
            Attributes.GetVertexPositions()[Vertex] = Points[Indices[Index + Corner]];
            const FVertexInstanceID Instance = Description.CreateVertexInstance(Vertex);
            Attributes.GetVertexInstanceNormals()[Instance] = Normal;
            Attributes.GetVertexInstanceTangents()[Instance] = Tangent;
            Attributes.GetVertexInstanceBinormalSigns()[Instance] = 1.0f;
            Attributes.GetVertexInstanceColors()[Instance] = FVector4f(1, 1, 1, 1);
            Attributes.GetVertexInstanceUVs().Set(Instance, 0, FVector2f::ZeroVector);
            Corners.Add(Instance);
        }
        Description.CreateTriangle(Group, Corners);
    }
    UStaticMesh* Mesh = NewObject<UStaticMesh>(Outer, NAME_None, RF_Transient);
    Mesh->bSupportRayTracing = false;
    Mesh->CreateBodySetup();
    // Render-only birds must bypass runtime triangle collision cooking entirely.
    Mesh->GetBodySetup()->bNeverNeedsCookedCollisionData = true;
    Mesh->GetStaticMaterials().Add(FStaticMaterial(Material, TEXT("Bird")));
    // These untextured meshes have constant zero UVs. Still mark the data as
    // initialized: cooked FastBuild does not run the editor streaming build.
    Mesh->GetStaticMaterials().Last().UVChannelData = FMeshUVChannelInfo(0.f);
    UStaticMesh::FBuildMeshDescriptionsParams Params;
    Params.bFastBuild = true; // The runtime path also works in cooked builds.
    Params.bBuildSimpleCollision = false;
    Params.bCommitMeshDescription = false;
    Params.bMarkPackageDirty = false;
    return Mesh->BuildFromMeshDescriptions({&Description}, Params) ? Mesh : nullptr;
}
}

AWindowBirds::AWindowBirds()
{
    PrimaryActorTick.bCanEverTick = true;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("BirdRoot")));
    MaterialSource = FSoftObjectPath(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
    for (int32 Bird = 0; Bird < 3; ++Bird)
    {
        UStaticMeshComponent* Body = CreateDefaultSubobject<UStaticMeshComponent>(
            *FString::Printf(TEXT("Bird%dBody"), Bird));
        Body->SetupAttachment(RootComponent);
        Body->SetRelativeScale3D(FVector(1.5f)); // A readable 93 cm wingspan at rooftop distance.
        Bodies.Add(Body);
        for (int32 Side = 0; Side < 2; ++Side)
        {
            UStaticMeshComponent* Wing = CreateDefaultSubobject<UStaticMeshComponent>(
                *FString::Printf(TEXT("Bird%dWing%d"), Bird, Side));
            Wing->SetupAttachment(Body);
            Wing->SetRelativeScale3D(FVector(1, Side == 0 ? 1 : -1, 1));
            Wings.Add(Wing);
        }
    }
    TArray<UStaticMeshComponent*> Parts;
    GetComponents(Parts);
    for (UStaticMeshComponent* Part : Parts)
    {
        Part->SetMobility(EComponentMobility::Movable);
        Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Part->SetCastShadow(false);
        Part->SetReceivesDecals(false);
        Part->SetVisibleInRayTracing(false);
        Part->bAffectDistanceFieldLighting = false;
        Part->bAffectDynamicIndirectLighting = false;
    }
    HideBirds();
}

void AWindowBirds::BeginPlay()
{
    Super::BeginPlay();
    UMaterialInterface* Source = MaterialSource.LoadSynchronous();
    if (!Source) return;
    Material = UMaterialInstanceDynamic::Create(Source, this);
    Material->SetVectorParameterValue(TEXT("Color"), FLinearColor(.012f, .016f, .022f));
    Material->SetScalarParameterValue(TEXT("Roughness"), 1.0f);
    // Body, head/beak and forked tail share one small closed mesh.
    BodyMesh = MakeBirdMesh(this, Material,
        {{14,0,1}, {3,3,0}, {-11,0,0}, {3,-3,0}, {3,0,3}, {3,0,-2},
         {-18,5,0}, {-15,0,0}, {-18,-5,0}},
        {0,1,4, 1,2,4, 2,3,4, 3,0,4, 1,0,5, 2,1,5, 3,2,5, 0,3,5,
         2,6,7, 2,7,8, 7,6,2, 8,7,2});
    // Swept, tapered wings with a thin closed edge, total span 62 cm.
    const TArray<FVector3f> Outline = {{7,0,0}, {5,11,0}, {-2,22,0},
        {-12,31,0}, {-8,16,0}, {-7,5,0}, {-5,0,0}};
    TArray<FVector3f> Points;
    TArray<int32> Indices;
    const int32 Count = Outline.Num();
    for (float Height : {.25f, -.25f})
        for (const FVector3f& Point : Outline) Points.Add(Point + FVector3f(0,0,Height));
    for (int32 Index = 1; Index < Count - 1; ++Index)
    {
        Indices.Append({0, Index, Index + 1, Count, Count + Index + 1, Count + Index});
    }
    for (int32 Index = 0; Index < Count; ++Index)
    {
        const int32 Next = (Index + 1) % Count;
        Indices.Append({Index, Count + Index, Next, Next, Count + Index, Count + Next});
    }
    WingMesh = MakeBirdMesh(this, Material, Points, Indices);
    for (UStaticMeshComponent* Body : Bodies) Body->SetStaticMesh(BodyMesh);
    for (UStaticMeshComponent* Wing : Wings) Wing->SetStaticMesh(WingMesh);
    if (!IsReady()) UE_LOG(LogTemp, Warning, TEXT("OOW_BIRDS runtime mesh build failed."));
}

void AWindowBirds::SetView(const FVector& CameraLocation, const FVector& CameraForward)
{
    ViewLocation = CameraLocation;
    ViewForward = FVector(CameraForward.X, CameraForward.Y, 0).GetSafeNormal();
    if (ViewForward.IsNearlyZero()) ViewForward = FVector::ForwardVector;
    ViewRight = FVector::CrossProduct(FVector::UpVector, ViewForward);
    bHasView = true;
    FlightAge = -1.0f;
    WaitRemaining = 7.5f;
    HideBirds();
}

void AWindowBirds::SetConditions(float Daylight, bool bFairWeather, const FVector& WindVelocity)
{
    const bool bNewPermitted = bFairWeather && Daylight > .55f && WindVelocity.Size2D() < 1400.0;
    Wind = FVector(WindVelocity.X, WindVelocity.Y, 0).GetClampedToMaxSize(1400.0);
    if (bPermitted && !bNewPermitted)
    {
        FlightAge = -1.0f;
        WaitRemaining = Random.FRandRange(22.0f, 38.0f);
        HideBirds();
    }
    bPermitted = bNewPermitted;
}

void AWindowBirds::HideBirds()
{
    for (UStaticMeshComponent* Body : Bodies) Body->SetVisibility(false, true);
}

int32 AWindowBirds::GetActiveCount() const
{
    int32 Count = 0;
    for (const UStaticMeshComponent* Body : Bodies) Count += Body->IsVisible() ? 1 : 0;
    return Count;
}

FVector AWindowBirds::GetFirstBirdLocation() const
{
    return Bodies[0]->GetComponentLocation();
}

void AWindowBirds::StartFlight()
{
    // The alley's sky is a narrow opening above/left of centre. Paths cross
    // behind its roofs; entries/exits stay offscreen, without a visible reset.
    const float Depth = CompletedFlights == 0 ? 5000.0f : Random.FRandRange(4500.0f, 5500.0f);
    const FVector Centre = ViewLocation + ViewForward * Depth - ViewRight * (Depth * .2f)
        + FVector::UpVector * (Depth * .38f);
    const float Direction = CompletedFlights == 0 || Random.FRand() > .5f ? 1.0f : -1.0f;
    FlightStart = Centre - ViewRight * (4600.0f * Direction) + FVector::UpVector * 25.0;
    FlightEnd = Centre + ViewRight * (4600.0f * Direction) - FVector::UpVector * 25.0;
    FlightDuration = 9200.0f / FMath::Clamp(1100.0f +
        static_cast<float>(FVector::DotProduct(Wind, ViewRight)) * Direction * .12f, 900.0f, 1300.0f);
    FlockSize = CompletedFlights == 0 ? 3 : Random.RandRange(1, 3);
    FlightAge = 0.0f;
}

void AWindowBirds::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!bHasView || !bPermitted || !IsReady()) return;
    const float Dt = FMath::Clamp(DeltaSeconds, 0.0f, .1f);
    if (FlightAge < 0)
    {
        WaitRemaining -= Dt;
        if (WaitRemaining > 0) return;
        StartFlight();
    }
    FlightAge += Dt;
    if (FlightAge > FlightDuration + (FlockSize - 1) * .42f)
    {
        HideBirds();
        ++CompletedFlights;
        FlightAge = -1.0f;
        WaitRemaining = Random.FRandRange(25.0f, 50.0f);
        return;
    }
    const FRotator Heading = (FlightEnd - FlightStart).Rotation();
    for (int32 Bird = 0; Bird < Bodies.Num(); ++Bird)
    {
        const float Age = FlightAge - Bird * .42f;
        const float Progress = Age / FlightDuration;
        const bool bVisible = Bird < FlockSize && Progress >= 0 && Progress <= 1;
        Bodies[Bird]->SetVisibility(bVisible, true);
        if (!bVisible) continue;
        const float Phase = Age * (Bird == 1 ? 4.2f : 4.6f) * 2 * PI + Bird;
        const float Glide = FMath::SmoothStep(.15f, .7f, FMath::Sin(Age * 1.55f + Bird * .8f));
        const float Flap = FMath::Lerp(FMath::Sin(Phase) * 38.0f, 7.0f, Glide);
        const FVector Position = FMath::Lerp(FlightStart, FlightEnd, Progress)
            + ViewForward * (Bird * 55.0f)
            + FVector::UpVector * (Bird * 24.0f + FMath::Sin(Progress * PI) * 45.0f
                                  + FMath::Sin(Phase) * (1.0f - Glide) * 1.2f);
        Bodies[Bird]->SetWorldLocationAndRotation(Position,
            FRotator(Heading.Pitch, Heading.Yaw, FMath::Sin(Age * .65f + Bird) * 5.0f));
        Wings[Bird * 2]->SetRelativeRotation(FRotator(0, 0, Flap));
        Wings[Bird * 2 + 1]->SetRelativeRotation(FRotator(0, 0, -Flap));
    }
    // Capture diagnostics distinguish timing, culling and roof occlusion.
    if (FlightAge >= FlightDuration * .5f && FlightAge - Dt < FlightDuration * .5f
        && FCString::Strifind(FCommandLine::Get(), TEXT("OOWCapture=")))
    {
        FVector2D Screen = FVector2D::ZeroVector;
        APlayerController* Controller = GetWorld()->GetFirstPlayerController();
        const bool bProjected = Controller && Controller->ProjectWorldLocationToScreen(GetFirstBirdLocation(), Screen);
        FHitResult Hit;
        const FCollisionQueryParams Query(SCENE_QUERY_STAT(OOWBirdSightline), true, this);
        const bool bBlocked = GetWorld()->LineTraceSingleByObjectType(Hit, ViewLocation, GetFirstBirdLocation(),
            FCollisionObjectQueryParams(FCollisionObjectQueryParams::AllObjects), Query);
        UE_LOG(LogTemp, Display, TEXT("OOW_BIRD_MIDPOINT age=%.2f world=%s screen=%s projected=%d blocked=%d blocker=%s visible=%d renderState=%d rendered=%d bounds=%s"),
            FlightAge, *GetFirstBirdLocation().ToString(), *Screen.ToString(), bProjected, bBlocked,
            *GetNameSafe(Hit.GetActor()), Bodies[0]->IsVisible(), Bodies[0]->IsRenderStateCreated(),
            Bodies[0]->WasRecentlyRendered(.25f), *Bodies[0]->Bounds.BoxExtent.ToString());
    }
}
