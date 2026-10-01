#include "WindowFrame.h"

#include "Camera/CameraComponent.h"
#include "Components/RectLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "MeshDescription.h"
#include "MeshUVChannelInfo.h"
#include "PhysicsEngine/BodySetup.h"
#include "StaticMeshAttributes.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
TAutoConsoleVariable<float> FrameRoomLumens(TEXT("oow.FrameRoomLumens"), 30.f,
    TEXT("Night indoor lamp lumens, calibrated to scene exposure; 0 disables the lamp."));
// Closed rounded extrusions, in camera-local centimetres (X forward, Y right).
// Meshes are rebuilt only when the camera projection changes.
struct FJoinery
{
    FMeshDescription Mesh;
    FStaticMeshAttributes Attributes{Mesh};
    FPolygonGroupID Groups[4];
    int32 Triangles = 0;

    explicit FJoinery(int32 MaterialCount = 4)
    {
        Attributes.Register();
        Attributes.GetVertexInstanceUVs().SetNumChannels(1);
        for (int32 I = 0; I < MaterialCount; ++I)
        {
            Groups[I] = Mesh.CreatePolygonGroup();
            Attributes.GetPolygonGroupMaterialSlotNames()[Groups[I]] = *FString::Printf(TEXT("Frame%d"), I);
        }
    }

    void Face(TArray<FVector3f> Points, const FVector3f& Outward, int32 Material, int32 GrainAxis,
        TArray<FVector3f> CornerNormals = {}, TArray<FVector2f> CornerUVs = {})
    {
        check(CornerNormals.IsEmpty() || CornerNormals.Num() == Points.Num());
        check(CornerUVs.IsEmpty() || CornerUVs.Num() == Points.Num());
        FVector3f Normal = FVector3f::CrossProduct(Points[1] - Points[0], Points[2] - Points[0]).GetSafeNormal();
        if (FVector3f::DotProduct(Normal, Outward) < 0)
        {
            // Reversing only three corners works for triangles/quads, but
            // would cross the perimeter of a rounded extrusion's end cap.
            for (int32 Index = 0; Index < Points.Num() / 2; ++Index)
            {
                const int32 Other = Points.Num() - 1 - Index;
                Swap(Points[Index], Points[Other]);
                if (!CornerNormals.IsEmpty()) Swap(CornerNormals[Index], CornerNormals[Other]);
                if (!CornerUVs.IsEmpty()) Swap(CornerUVs[Index], CornerUVs[Other]);
            }
            Normal *= -1;
        }
        TArray<FVertexInstanceID> Corners;
        for (int32 Index = 0; Index < Points.Num(); ++Index)
        {
            const FVector3f& Point = Points[Index];
            const FVector3f VertexNormal = CornerNormals.IsEmpty() ? Normal : CornerNormals[Index];
            // U across / V along each extrusion, including its flat end grain.
            FVector3f Along = FVector3f::ZeroVector; Along[GrainAxis] = 1;
            if (FMath::Abs(FVector3f::DotProduct(Along, VertexNormal)) > .95f)
                Along = FVector3f(1, 0, 0);
            const FVector3f Tangent = FVector3f::CrossProduct(Along, VertexNormal).GetSafeNormal();
            const FVector3f Bitangent = FVector3f::CrossProduct(VertexNormal, Tangent);
            const FVertexID Vertex = Mesh.CreateVertex();
            Attributes.GetVertexPositions()[Vertex] = Point;
            const FVertexInstanceID Instance = Mesh.CreateVertexInstance(Vertex);
            Attributes.GetVertexInstanceNormals()[Instance] = VertexNormal;
            Attributes.GetVertexInstanceTangents()[Instance] = Tangent;
            Attributes.GetVertexInstanceBinormalSigns()[Instance] = 1;
            Attributes.GetVertexInstanceColors()[Instance] = FVector4f(1, 1, 1, 1);
            Attributes.GetVertexInstanceUVs().Set(Instance, 0, CornerUVs.IsEmpty() ? FVector2f(
                FVector3f::DotProduct(Point, Tangent), FVector3f::DotProduct(Point, Bitangent)) : CornerUVs[Index]);
            Corners.Add(Instance);
        }
        for (int32 I = 1; I < Corners.Num() - 1; ++I)
        {
            // UE's left-handed triangle normal is cross(P2-P0, P1-P0).
            // Keep the outward shading normal and front-face winding aligned.
            Mesh.CreateTriangle(Groups[Material], {Corners[0], Corners[I + 1], Corners[I]});
            ++Triangles;
        }
    }

    void Box(FVector3f Centre, FVector3f Half, float Bevel, int32 Material = 0)
    {
        const int32 GrainAxis = Half.Y > Half.Z ? 1 : 2;
        const int32 A = (GrainAxis + 1) % 3, B = (GrainAxis + 2) % 3;
        const float R = FMath::Min(Bevel, Half.GetMin() * .8f);
        const FVector3f Core = Half - FVector3f(R);
        constexpr int32 ArcSegments = 4;
        TArray<FVector3f> Section, Normals;
        TArray<float> Distances;
        float Perimeter = 0;
        // A rounded rectangle extruded along the piece's length. Shared arc
        // endpoints have the same analytic normal and tangent on both strips.
        for (int32 Corner = 0; Corner < 4; ++Corner)
        {
            const float SA = Corner == 0 || Corner == 3 ? 1.f : -1.f;
            const float SB = Corner < 2 ? 1.f : -1.f;
            for (int32 Step = 0; Step <= ArcSegments; ++Step)
            {
                const float Angle = (Corner + float(Step) / ArcSegments) * HALF_PI;
                float Sin, Cos;
                FMath::SinCos(&Sin, &Cos, Angle);
                // Exact cardinal endpoints keep the flats and bounds exact.
                if (FMath::Abs(Sin) < 1.e-6f) Sin = 0;
                if (FMath::Abs(Cos) < 1.e-6f) Cos = 0;
                FVector3f N = FVector3f::ZeroVector; N[A] = Cos; N[B] = Sin;
                FVector3f P = Centre; P[A] += SA * Core[A] + R * Cos; P[B] += SB * Core[B] + R * Sin;
                Section.Add(P);
                Normals.Add(N.GetSafeNormal());
                Distances.Add(Perimeter + R * HALF_PI * Step / ArcSegments);
            }
            Perimeter += R * HALF_PI + 2 * Core[Corner % 2 == 0 ? A : B];
        }
        for (int32 Index = 0; Index < Section.Num(); ++Index)
        {
            const int32 Next = (Index + 1) % Section.Num();
            FVector3f P0 = Section[Index], P1 = Section[Index], P2 = Section[Next], P3 = Section[Next];
            P0[GrainAxis] -= Half[GrainAxis]; P1[GrainAxis] += Half[GrainAxis];
            P2[GrainAxis] += Half[GrainAxis]; P3[GrainAxis] -= Half[GrainAxis];
            const float U0 = Distances[Index], U1 = Next == 0 ? Perimeter : Distances[Next];
            // Arc length gives centimetre UVs that stay continuous as the
            // tangent rotates; the only wrap lies on the upper/back flat.
            Face({P0, P1, P2, P3}, Normals[Index] + Normals[Next], Material, GrainAxis,
                {Normals[Index], Normals[Index], Normals[Next], Normals[Next]},
                {{U0, P0[GrainAxis]}, {U0, P1[GrainAxis]}, {U1, P2[GrainAxis]}, {U1, P3[GrainAxis]}});
        }
        // Flat closed ends retain the physical butt joints between pieces.
        for (float Sign : {-1.f, 1.f})
        {
            FVector3f CapCentre = Centre; CapCentre[GrainAxis] += Sign * Half[GrainAxis];
            FVector3f N = FVector3f::ZeroVector; N[GrainAxis] = Sign;
            for (int32 Index = 0; Index < Section.Num(); ++Index)
            {
                FVector3f P0 = Section[Index], P1 = Section[(Index + 1) % Section.Num()];
                P0[GrainAxis] += Sign * Half[GrainAxis]; P1[GrainAxis] += Sign * Half[GrainAxis];
                // A centre fan avoids tiny near-collinear triangles on the
                // small seals, while keeping the entire end in one plane.
                Face({CapCentre, P0, P1}, N, Material, GrainAxis);
            }
        }
    }

    void Ring(float X, float Depth, float W, float H, float Width, int32 Material, float Bevel, float CentreY = 0)
    {
        for (float Side : {-1.f, 1.f})
        {
            Box({X, CentreY + Side * (W + Width * .5f), 0}, {Depth * .5f, Width * .5f, H + Width}, Bevel, Material);
            // Butt joints retain a fine physical seam between the horizontal and vertical pieces.
            Box({X, CentreY, Side * (H + Width * .5f)}, {Depth * .5f, W - .025f, Width * .5f}, Bevel, Material);
        }
    }

    UStaticMesh* Build(UObject* Owner, const TArray<TObjectPtr<UMaterialInstanceDynamic>>& Materials)
    {
        UStaticMesh* Result = NewObject<UStaticMesh>(Owner, NAME_None, RF_Transient);
        Result->CreateBodySetup();
        Result->GetBodySetup()->bNeverNeedsCookedCollisionData = true;
        for (int32 I = 0; I < Materials.Num(); ++I)
        {
            Result->GetStaticMaterials().Add(FStaticMaterial(Materials[I], *FString::Printf(TEXT("Frame%d"), I)));
            // FastBuild skips editor UV-density generation in cooked games.
            // Both joinery and glass use one world centimetre per UV unit.
            Result->GetStaticMaterials().Last().UVChannelData = FMeshUVChannelInfo(1.f);
        }
        UStaticMesh::FBuildMeshDescriptionsParams Params;
        Params.bFastBuild = true;
        Params.bBuildSimpleCollision = false;
        Params.bCommitMeshDescription = false;
        Params.bMarkPackageDirty = false;
        return Result->BuildFromMeshDescriptions({&Mesh}, Params) ? Result : nullptr;
    }
};
}

AWindowFrame::AWindowFrame()
{
    PrimaryActorTick.bCanEverTick = false;
    Frame = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("PhysicalWindowFrame"));
    SetRootComponent(Frame);
    Frame->SetMobility(EComponentMobility::Movable);
    Frame->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Frame->SetReceivesDecals(false);
    // The room walls provide the occlusion; daylight uses the actual scene lights.
    Frame->SetLightingChannels(true, false, false);
    MaterialSource = FSoftObjectPath(TEXT("/Game/Materials/OOW/DesktopFrame/M_DesktopFrame.M_DesktopFrame"));
    // Reuse cooked solid meshes: runtime FastBuild joinery has no distance fields
    // or Lumen surface cards, so it cannot serve as a reliable room enclosure.
    static ConstructorHelpers::FObjectFinder<UStaticMesh> WallMesh(TEXT("/Engine/BasicShapes/Cube.Cube"));
    for (int32 I = 0; I < 9; ++I)
    {
        UStaticMeshComponent* Wall = CreateDefaultSubobject<UStaticMeshComponent>(*FString::Printf(TEXT("RoomWall%d"), I));
        Wall->SetupAttachment(Frame);
        Wall->SetMobility(EComponentMobility::Movable);
        Wall->SetStaticMesh(WallMesh.Object);
        Wall->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Wall->SetReceivesDecals(false);
        Wall->SetCastShadow(true);
        Wall->bAffectDistanceFieldLighting = true;
        Wall->bVisibleInRayTracing = true;
        RoomWalls.Add(Wall);
    }
    RainGlass = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("WindowRainGlass"));
    RainGlass->SetupAttachment(Frame);
    RainGlass->SetMobility(EComponentMobility::Movable);
    RainGlass->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    RainGlass->SetReceivesDecals(false);
    RainGlass->SetCastShadow(false);
    RainGlass->SetVisibility(false);
    RainGlass->bVisibleInRayTracing = false;
    RainMaterialSource = FSoftObjectPath(TEXT("/Game/Materials/OOW/DesktopFrame/M_WindowRainGlass.M_WindowRainGlass"));
    RoomBounce = CreateDefaultSubobject<URectLightComponent>(TEXT("IndoorBounce"));
    RoomBounce->SetupAttachment(Frame);
    RoomBounce->SetMobility(EComponentMobility::Movable);
    const FVector LampPosition(-250, -90, 110);
    RoomBounce->SetRelativeLocation(LampPosition);
    RoomBounce->SetRelativeRotation((FVector(94, 0, 0) - LampPosition).Rotation());
    RoomBounce->SetSourceWidth(120);
    RoomBounce->SetSourceHeight(70);
    RoomBounce->SetAttenuationRadius(600);
    RoomBounce->SetIntensityUnits(ELightUnits::Lumens);
    RoomBounce->SetUseTemperature(true);
    RoomBounce->SetTemperature(4000);
    RoomBounce->SetLightingChannels(true, false, false);
    RoomBounce->SetCastShadows(true);
    RoomBounce->SetAffectTranslucentLighting(false);
    RoomBounce->SetIndirectLightingIntensity(1);
    RoomBounce->SetVolumetricScatteringIntensity(0);
    SetDaylight(1);
    Tags.Add(TEXT("OOWDesktopFrame"));
}

void AWindowFrame::BeginPlay()
{
    Super::BeginPlay();
    UMaterialInterface* Source = MaterialSource.LoadSynchronous();
    if (!Source) { UE_LOG(LogTemp, Error, TEXT("OOW_FRAME missing DesktopFrame material; run build_desktop_frame.py")); return; }
    for (int32 I = 0; I < 4; ++I)
    {
        UMaterialInstanceDynamic* Material = UMaterialInstanceDynamic::Create(Source, this);
        if (I > 0)
        {
            Material->SetVectorParameterValue(TEXT("Color"), I == 1 ? FLinearColor(.009f, .012f, .011f)
                : I == 2 ? FLinearColor(.055f, .062f, .065f) : FLinearColor(.42f, .41f, .37f));
            Material->SetScalarParameterValue(TEXT("Roughness"), I == 1 ? .83f : I == 2 ? .32f : .68f);
            Material->SetScalarParameterValue(TEXT("Metallic"), I == 2 ? .65f : 0);
            Material->SetScalarParameterValue(TEXT("Grain"), 0);
        }
        Materials.Add(Material);
    }
    SetStyle(StyleId);
    RoomMaterial = UMaterialInstanceDynamic::Create(Source, this);
    RoomMaterial->SetVectorParameterValue(TEXT("Color"), FLinearColor(.55f, .53f, .49f));
    RoomMaterial->SetScalarParameterValue(TEXT("Roughness"), .85f);
    RoomMaterial->SetScalarParameterValue(TEXT("Metallic"), 0);
    RoomMaterial->SetScalarParameterValue(TEXT("Grain"), 0);
    for (UStaticMeshComponent* Wall : RoomWalls) Wall->SetMaterial(0, RoomMaterial);
    if (UMaterialInterface* RainSource = RainMaterialSource.LoadSynchronous())
    {
        RainMaterial = UMaterialInstanceDynamic::Create(RainSource, this);
        SetRainIntensity(RainIntensity);
    }
    else UE_LOG(LogTemp, Error, TEXT("OOW_FRAME missing rain glass material; run build_desktop_frame.py"));
}

bool AWindowFrame::SetStyle(FName Id)
{
    const bool bIvory = Id == TEXT("ivory"), bGraphite = Id == TEXT("graphite");
    if (Id != TEXT("oak") && !bIvory && !bGraphite) return false;
    StyleId = Id;
    if (Materials.Num() == 4)
    {
        Materials[0]->SetVectorParameterValue(TEXT("Color"), bIvory ? FLinearColor(.65f, .59f, .46f)
            : bGraphite ? FLinearColor(.048f, .055f, .063f) : FLinearColor(.19f, .105f, .051f));
        Materials[0]->SetScalarParameterValue(TEXT("Roughness"), bIvory ? .48f : bGraphite ? .46f : .39f);
        // The visible finish is dielectric powder coating over aluminium.
        Materials[0]->SetScalarParameterValue(TEXT("Metallic"), 0);
        Materials[0]->SetScalarParameterValue(TEXT("Grain"), bIvory || bGraphite ? 0 : 1);
    }
    return true;
}

void AWindowFrame::FitToView(UCameraComponent* Camera, float AspectRatio)
{
    if (!Camera || Materials.Num() != 4 || !RainMaterial || !FMath::IsFinite(AspectRatio) || AspectRatio <= 0) return;
    AttachToComponent(Camera, FAttachmentTransformRules::SnapToTargetNotIncludingScale);
    const float Fov = Camera->FieldOfView;
    if (FMath::IsNearlyEqual(Fov, LastFov) && FMath::IsNearlyEqual(AspectRatio, LastAspect)) return;
    const float TanX = FMath::Tan(FMath::DegreesToRadians(Fov * .5f)), TanY = TanX / AspectRatio;
    const float W = 92 * TanX - 3.4f, H = 92 * TanY - 3.4f;
    if (W < 6 || H < 6) return;
    FJoinery Geometry;
    // Contemporary residential extrusion: fixed light plus a 22% right casement.
    // Narrow stepped profiles and EPDM seals replace the old central crossbar.
    Geometry.Ring(92, 6, W, H, 12, 0, .14f);
    Geometry.Ring(94.8f, .5f, W - .35f, H - .35f, .4f, 1, .05f);
    Geometry.Ring(95.2f, .8f, W - 1.05f, H - 1.05f, .7f, 0, .08f);
    Geometry.Ring(95.7f, .3f, W - 1.25f, H - 1.25f, .24f, 1, .04f);
    const float Mullion = .56f * (W - 1.25f);
    Geometry.Box({93.7f, Mullion, 0}, {1.65f, .65f, H - 1.05f}, .12f);
    Geometry.Box({95.6f, Mullion, 0}, {.2f, .83f, H - 1.05f}, .05f, 1);
    const float CasementCentre = (Mullion + W) * .5f;
    const float CasementHalf = (W - Mullion) * .5f - 1.4f;
    Geometry.Ring(93.9f, 2.8f, CasementHalf, H - 2.6f, 1.15f, 0, .11f, CasementCentre);
    Geometry.Ring(95.6f, .3f, CasementHalf - .2f, H - 2.8f, .24f, 1, .04f, CasementCentre);
    // Pale stone sill and a restrained vertical lever on the opening sash.
    Geometry.Box({88, 0, -H - .75f}, {7, W + 12, .85f}, .2f, 3);
    Geometry.Box({82.5f, 0, -H - 1.7f}, {1.2f, W + 12, .12f}, .05f, 1);
    const float HandleY = Mullion + 1.2f;
    Geometry.Box({92.0f, HandleY, -H * .08f}, {.3f, .38f, 1.15f}, .13f, 2);
    Geometry.Box({91.3f, HandleY, -H * .08f + .7f}, {.6f, .2f, .23f}, .10f, 2);
    Geometry.Box({90.7f, HandleY, -H * .08f - .5f}, {.23f, .23f, 1.3f}, .15f, 2);
    for (float Side : {-1.f, 1.f})
        Geometry.Box({92.6f, W - .65f, Side * H * .6f}, {.33f, .28f, .9f}, .12f, 2);

    // One physical pane behind the joinery; depth testing masks every frame rail.
    // It extends behind the profiles to prevent perspective gaps. UV0=(-Y,+Z)
    // in centimetres keeps droplets the same size at every viewport aspect.
    FJoinery GlassGeometry(1);
    const float GW = 96 * TanX, GH = 96 * TanY;
    GlassGeometry.Face({{96,-GW,-GH}, {96,GW,-GH}, {96,GW,GH}, {96,-GW,GH}}, {-1,0,0}, 0, 2);
    UStaticMesh* Mesh = Geometry.Build(this, Materials);
    UStaticMesh* GlassMesh = GlassGeometry.Build(this, {RainMaterial});
    if (!Mesh || !GlassMesh) return;
    Frame->SetStaticMesh(Mesh);
    RainGlass->SetStaticMesh(GlassMesh);
    // Front wall has a real opening, overlapped by the outer frame profile.
    // All panels are closed 30 cm solids; the camera and lamp are inside.
    const float HoleW = W + 8, HoleH = H + 8;
    const float RoomW = FMath::Max(220.f, W + 80), RoomH = FMath::Max(180.f, H + 80);
    auto Wall = [this](int32 Index, FVector Centre, FVector Half)
    {
        RoomWalls[Index]->SetRelativeLocation(Centre);
        RoomWalls[Index]->SetRelativeScale3D(Half / 50); // Native cube is 100 cm.
    };
    for (int32 Side = 0; Side < 2; ++Side)
    {
        const float Sign = Side == 0 ? -1.f : 1.f;
        Wall(Side, {80, Sign * (RoomW + HoleW) * .5f, 0}, {15, (RoomW - HoleW) * .5f, RoomH});
        Wall(2 + Side, {80, 0, Sign * (RoomH + HoleH) * .5f}, {15, HoleW, (RoomH - HoleH) * .5f});
        Wall(4 + Side, {-125, Sign * (RoomW + 15), 0}, {220, 15, RoomH + 30});
        Wall(6 + Side, {-125, 0, Sign * (RoomH + 15)}, {220, RoomW + 30, 15});
    }
    Wall(8, {-330, 0, 0}, {15, RoomW + 30, RoomH + 30});
    TriangleCount = Geometry.Triangles;
    OpeningSize = FVector2D((W - 1.25f) * 2, (H - 1.25f) * 2);
    LastFov = Fov; LastAspect = AspectRatio;
}

void AWindowFrame::SetDaylight(float Daylight)
{
    const float Day = FMath::IsFinite(Daylight) ? FMath::Clamp(Daylight, 0.f, 1.f) : 1.f;
    const float Lamp = FMath::Clamp(FrameRoomLumens.GetValueOnGameThread(), 0.f, 3000.f);
    // Match the scene's occupied-window dusk transition. During the day only
    // sunlight, skylight and their Lumen bounces illuminate the frame and room.
    RoomBounce->SetIntensity(Lamp * FMath::SmoothStep(.58f, .86f, 1.f - Day));
}

float AWindowFrame::GetRoomLampLumens() const
{
    return RoomBounce->Intensity;
}

void AWindowFrame::SetRainIntensity(float Intensity)
{
    RainIntensity = FMath::IsFinite(Intensity) ? FMath::Clamp(Intensity, 0.f, 1.f) : 0;
    if (RainMaterial) RainMaterial->SetScalarParameterValue(TEXT("RainIntensity"), RainIntensity);
    RainGlass->SetVisibility(RainIntensity > 0);
}

bool AWindowFrame::IsReady() const
{
    if (Materials.Num() != 4 || !RainMaterial || !RainGlass->GetStaticMesh()
        || !Frame->GetStaticMesh() || !Frame->IsVisible() || IsHidden()) return false;
    for (const FStaticMaterial& Slot : Frame->GetStaticMesh()->GetStaticMaterials())
        if (!Slot.UVChannelData.bInitialized) return false;
    if (!RainGlass->GetStaticMesh()->GetStaticMaterials()[0].UVChannelData.bInitialized) return false;
    if (!RoomMaterial || RoomWalls.Num() != 9) return false;
    for (const UStaticMeshComponent* Wall : RoomWalls)
        if (!Wall->GetStaticMesh() || !Wall->IsVisible()) return false;
    return true;
}
