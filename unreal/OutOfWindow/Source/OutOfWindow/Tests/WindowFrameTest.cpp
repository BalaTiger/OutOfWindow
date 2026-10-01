#if WITH_DEV_AUTOMATION_TESTS

#include "../WindowFrame.h"
#include "../WindowVisibilityButton.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/RectLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/App.h"
#include "Misc/AutomationTest.h"
#include "StaticMeshResources.h"
#include "UObject/UObjectGlobals.h"
#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWindowFrameTest, "OutOfWindow.Frame.ProjectionAndUIIndependence",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWindowFrameTest::RunTest(const FString& Parameters)
{
    if (!TestTrue(TEXT("Slate is available"), FSlateApplication::IsInitialized())) return false;
    if (!TestNotNull(TEXT("Desktop frame material is available"), LoadObject<UMaterialInterface>(nullptr,
        TEXT("/Game/Materials/OOW/DesktopFrame/M_DesktopFrame.M_DesktopFrame")))) return false;
    if (!TestNotNull(TEXT("Rain glass material is available"), LoadObject<UMaterialInterface>(nullptr,
        TEXT("/Game/Materials/OOW/DesktopFrame/M_WindowRainGlass.M_WindowRainGlass")))) return false;
    UWorld* World = UWorld::CreateWorld(EWorldType::Game, false);
    if (!TestNotNull(TEXT("Test world"), World)) return false;
    ACameraActor* Camera = World->SpawnActor<ACameraActor>();
    AWindowFrame* Frame = World->SpawnActor<AWindowFrame>();
    if (!TestNotNull(TEXT("Camera actor"), Camera) || !TestNotNull(TEXT("Frame actor"), Frame))
    {
        World->DestroyWorld(false);
        return false;
    }
    Camera->SetActorLocation(FVector(-2000, -20800, 2300));
    Camera->SetActorRotation(FRotator(-8, 55, 0));
    Frame->DispatchBeginPlay();
    UCameraComponent* View = Camera->GetCameraComponent();
    auto Fit = [Frame, View](float Aspect)
    {
        const float HorizontalFov = FMath::RadiansToDegrees(2.f * FMath::Atan(
            FMath::Tan(FMath::DegreesToRadians(55.f * .5f)) * Aspect));
        View->SetFieldOfView(HorizontalFov);
        View->SetAspectRatio(Aspect);
        Frame->FitToView(View, Aspect);
    };
    Fit(16.f / 9.f);
    if (!TestTrue(TEXT("Runtime joinery mesh and materials are ready"), Frame->IsReady()))
    {
        World->DestroyWorld(false);
        return false;
    }
    UStaticMeshComponent* Component = Cast<UStaticMeshComponent>(Frame->GetRootComponent());
    UStaticMeshComponent* RainGlass = nullptr;
    TArray<UStaticMeshComponent*> RoomWalls;
    TArray<UStaticMeshComponent*> MeshComponents;
    Frame->GetComponents(MeshComponents);
    for (UStaticMeshComponent* MeshComponent : MeshComponents)
    {
        if (MeshComponent->GetFName() == TEXT("WindowRainGlass")) RainGlass = MeshComponent;
        if (MeshComponent->GetName().StartsWith(TEXT("RoomWall"))) RoomWalls.Add(MeshComponent);
    }
    if (!TestNotNull(TEXT("Frame root mesh component"), Component)
        || !TestNotNull(TEXT("Named rain glass component"), RainGlass))
    {
        World->DestroyWorld(false);
        return false;
    }
    URectLightComponent* RoomBounce = nullptr;
    TArray<URectLightComponent*> Lights;
    Frame->GetComponents(Lights);
    for (URectLightComponent* Light : Lights)
        if (Light->GetFName() == TEXT("IndoorBounce")) RoomBounce = Light;
    if (!TestNotNull(TEXT("Indoor room light"), RoomBounce))
    {
        World->DestroyWorld(false);
        return false;
    }
    TestTrue(TEXT("Room light shares the standard scene lighting channel"), RoomBounce->LightingChannels.bChannel0
        && !RoomBounce->LightingChannels.bChannel1 && !RoomBounce->LightingChannels.bChannel2);
    TestTrue(TEXT("Frame receives natural scene lighting"), Component->LightingChannels.bChannel0
        && !Component->LightingChannels.bChannel1 && !Component->LightingChannels.bChannel2);
    TestTrue(TEXT("Walls physically shadow the room light"), RoomBounce->CastShadows);
    TestEqual(TEXT("Room light participates in indirect lighting"), RoomBounce->IndirectLightingIntensity, 1.f);
    TestEqual(TEXT("Room light cannot brighten outdoor volumetric fog"), RoomBounce->VolumetricScatteringIntensity, 0.f);
    TestFalse(TEXT("Room light cannot spill onto outdoor glass or precipitation"), RoomBounce->bAffectTranslucentLighting);
    TestTrue(TEXT("Frame follows the camera independently of world placement"), Component->GetAttachParent() == View);
    TestEqual(TEXT("Frame cannot collide with the scene"), Component->GetCollisionEnabled(), ECollisionEnabled::NoCollision);
    UStaticMesh* RoomCube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
    TestNotNull(TEXT("Room uses the native cube mesh"), RoomCube);
    TestEqual(TEXT("Room has four window surrounds and five enclosing surfaces"), RoomWalls.Num(), 9);
    auto CheckRoom = [&]()
    {
        TArray<FBox> WallBounds;
        FBox Enclosure(ForceInit);
        const FVector Lamp = RoomBounce->GetRelativeLocation();
        const FVector2D HalfOpening = Frame->GetOpeningSize() * .5;
        int32 FrontWalls = 0;
        for (UStaticMeshComponent* Wall : RoomWalls)
        {
            TestTrue(TEXT("Room wall remains attached to the frame"), Wall->GetAttachParent() == Component);
            TestTrue(TEXT("Room resizing reuses the native cube"), Wall->GetStaticMesh() == RoomCube);
            TestTrue(TEXT("Room wall is visible and casts physical shadows"), Wall->IsVisible() && Wall->CastShadow);
            TestTrue(TEXT("Room wall participates in distance fields and ray tracing"), Wall->bAffectDistanceFieldLighting && Wall->bVisibleInRayTracing);
            TestTrue(TEXT("Room wall shares scene lighting"), Wall->LightingChannels.bChannel0
                && !Wall->LightingChannels.bChannel1 && !Wall->LightingChannels.bChannel2);
            TestEqual(TEXT("Room wall follows the movable camera"), Wall->GetMobility(), EComponentMobility::Movable);
            TestEqual(TEXT("Room wall cannot collide with scene content"), Wall->GetCollisionEnabled(), ECollisionEnabled::NoCollision);
            if (!TestNotNull(TEXT("Room wall has its cube mesh"), Wall->GetStaticMesh().Get())) continue;
            TestNotNull(TEXT("Room wall has a surface material"), Wall->GetMaterial(0));
            const FBox Bounds = Wall->GetStaticMesh()->GetBoundingBox().TransformBy(Wall->GetRelativeTransform());
            WallBounds.Add(Bounds);
            Enclosure += Bounds;
            TestFalse(TEXT("Camera is outside every wall volume"), Bounds.IsInsideOrOn(FVector::ZeroVector));
            TestFalse(TEXT("Indoor lamp is outside every wall volume"), Bounds.IsInsideOrOn(Lamp));
            if (Bounds.Min.X > 0)
            {
                ++FrontWalls;
                const FBox Aperture(FVector(Bounds.Min.X, -HalfOpening.X, -HalfOpening.Y),
                    FVector(Bounds.Max.X, HalfOpening.X, HalfOpening.Y));
                TestFalse(TEXT("Front wall leaves the entire window opening clear"), Bounds.Intersect(Aperture));
                TestTrue(TEXT("Window joinery is seated in the front wall"), Bounds.Intersect(Component->GetStaticMesh()->GetBoundingBox()));
            }
        }
        TestEqual(TEXT("Four wall pieces surround the window opening"), FrontWalls, 4);
        TestTrue(TEXT("Camera is inside the room enclosure"), Enclosure.IsInside(FVector::ZeroVector));
        TestTrue(TEXT("Indoor lamp is inside the room enclosure"), Enclosure.IsInside(Lamp));
        for (const FVector& Direction : {FVector(1,0,0), FVector(-1,0,0), FVector(0,1,0), FVector(0,-1,0), FVector(0,0,1), FVector(0,0,-1)})
        {
            const FVector End = Direction * Enclosure.GetSize().GetMax() * 2;
            bool bBlocked = false;
            for (const FBox& Bounds : WallBounds)
                bBlocked |= FMath::LineBoxIntersection(Bounds, FVector::ZeroVector, End, End);
            TestEqual(FString::Printf(TEXT("Camera axis %s escapes only through the window"), *Direction.ToString()), bBlocked, Direction.X != 1);
        }
    };
    CheckRoom();
    if (RoomCube && FApp::CanEverRender())
    {
        const FStaticMeshRenderData* Data = RoomCube->GetRenderData();
        if (TestTrue(TEXT("Room cube has render data"), Data && Data->LODResources.Num() > 0))
        {
            TestNotNull(TEXT("Room cube has distance-field occlusion data"), Data->LODResources[0].DistanceFieldData);
            TestNotNull(TEXT("Room cube has Lumen surface-card data"), Data->LODResources[0].CardRepresentationData);
        }
    }
    TestTrue(TEXT("Rain glass is a distinct child of the frame"), RainGlass != Component && RainGlass->GetAttachParent() == Component);
    TestTrue(TEXT("Glass and joinery share camera-local coordinates"), RainGlass->GetRelativeTransform().Equals(FTransform::Identity));
    TestEqual(TEXT("Rain glass cannot collide with the scene"), RainGlass->GetCollisionEnabled(), ECollisionEnabled::NoCollision);
    TestFalse(TEXT("Rain glass cannot cast a shadow over the view"), RainGlass->CastShadow);
    for (const FStaticMaterial& Slot : RainGlass->GetStaticMesh()->GetStaticMaterials())
        TestTrue(TEXT("Rain glass supplies initialized UV streaming data"), Slot.UVChannelData.bInitialized);
    for (const FStaticMaterial& Slot : Component->GetStaticMesh()->GetStaticMaterials())
        TestTrue(TEXT("Every runtime material slot supplies initialized UV streaming data"), Slot.UVChannelData.bInitialized);
    const int32 Triangles = Frame->GetTriangleCount();
    TestTrue(TEXT("Joinery contains geometry"), Triangles > 0);
    const FVector2D WideOpening = Frame->GetOpeningSize();
    TestTrue(TEXT("Landscape window has a usable opening"), WideOpening.X > WideOpening.Y && WideOpening.Y > 0);
    auto CheckWinding = [&]()
    {
        for (UStaticMeshComponent* Part : {Component, RainGlass})
        {
            const FStaticMeshRenderData* Data = Part->GetStaticMesh()->GetRenderData();
            if (!TestTrue(Part->GetName() + TEXT(" has runtime render data"), Data && Data->LODResources.Num() > 0)) continue;
            const FStaticMeshLODResources& LOD = Data->LODResources[0];
            const FIndexArrayView Indices = LOD.IndexBuffer.GetArrayView();
            if (!TestTrue(Part->GetName() + TEXT(" has readable triangle indices"), Indices.Num() > 0 && Indices.Num() % 3 == 0)) continue;
            int32 InvalidTriangle = INDEX_NONE;
            for (int32 Index = 0; Index < Indices.Num(); Index += 3)
            {
                const uint32 A = Indices[Index], B = Indices[Index + 1], C = Indices[Index + 2];
                const auto& Positions = LOD.VertexBuffers.PositionVertexBuffer;
                const auto& Vertices = LOD.VertexBuffers.StaticMeshVertexBuffer;
                if (FMath::Max3(A, B, C) >= Positions.GetNumVertices() || FMath::Max3(A, B, C) >= Vertices.GetNumVertices())
                {
                    InvalidTriangle = Index / 3;
                    break;
                }
                // Match FStaticMeshOperations: UE's left-handed geometry uses
                // the reverse cross product. Outward normals alone cannot catch reversed culling.
                const FVector3f FaceNormal = FVector3f::CrossProduct(Positions.VertexPosition(C) - Positions.VertexPosition(A),
                    Positions.VertexPosition(B) - Positions.VertexPosition(A)).GetSafeNormal();
                for (uint32 Vertex : {A, B, C})
                {
                    const FVector4f PackedNormal = Vertices.VertexTangentZ(Vertex);
                    const FVector3f Normal(PackedNormal.X, PackedNormal.Y, PackedNormal.Z);
                    const FVector4f PackedTangent = Vertices.VertexTangentX(Vertex);
                    const FVector3f Tangent(PackedTangent.X, PackedTangent.Y, PackedTangent.Z);
                    const FVector2f UV = Vertices.GetVertexUV(Vertex, 0);
                    // Analytic rounded normals differ from their chord's face
                    // normal by at most half of one 22.5-degree arc segment.
                    if (Positions.VertexPosition(Vertex).ContainsNaN() || Normal.ContainsNaN() || Tangent.ContainsNaN()
                        || !FMath::IsFinite(UV.X) || !FMath::IsFinite(UV.Y)
                        || !FMath::IsNearlyEqual(Normal.SizeSquared(), 1.f, .025f)
                        || !FMath::IsNearlyEqual(Tangent.SizeSquared(), 1.f, .025f)
                        || FMath::Abs(FVector3f::DotProduct(Normal, Tangent)) > .025f
                        || !FMath::IsNearlyEqual(FMath::Abs(PackedNormal.W), 1.f, .01f)
                        || !(FVector3f::DotProduct(FaceNormal, Normal.GetSafeNormal()) > .97f))
                        InvalidTriangle = Index / 3;
                }
                if (InvalidTriangle != INDEX_NONE) break;
            }
            TestTrue(FString::Printf(TEXT("%s rendered winding and finite tangent basis agree with its surface (first invalid triangle: %d)"),
                *Part->GetName(), InvalidTriangle), InvalidTriangle == INDEX_NONE);
        }
    };
    auto CheckRoundedProfiles = [&]()
    {
        const FStaticMeshRenderData* Data = Component->GetStaticMesh()->GetRenderData();
        if (!Data || Data->LODResources.IsEmpty()) return;
        const FStaticMeshLODResources& LOD = Data->LODResources[0];
        const auto& Positions = LOD.VertexBuffers.PositionVertexBuffer;
        const auto& Vertices = LOD.VertexBuffers.StaticMeshVertexBuffer;
        auto PositionKey = [](const FVector3f& Point)
        {
            // Weld render instances by position, independent of UV seams and
            // the intentionally hard normals on each piece's flat end.
            return FIntVector(FMath::RoundToInt(Point.X * 10000), FMath::RoundToInt(Point.Y * 10000),
                FMath::RoundToInt(Point.Z * 10000));
        };
        struct FSharedCorner
        {
            FVector3f Normal = FVector3f::ZeroVector, Tangent = FVector3f::ZeroVector;
            int32 Count = 0;
            bool bCurved = false;
        };
        TMap<FIntVector, FSharedCorner> AlongY, AlongZ;
        bool bContinuous = true;
        for (uint32 Vertex = 0; Vertex < Vertices.GetNumVertices(); ++Vertex)
        {
            const FVector4f PackedNormal = Vertices.VertexTangentZ(Vertex);
            const FVector4f PackedTangent = Vertices.VertexTangentX(Vertex);
            const FVector3f Normal = FVector3f(PackedNormal.X, PackedNormal.Y, PackedNormal.Z).GetSafeNormal();
            const FVector3f Tangent = FVector3f(PackedTangent.X, PackedTangent.Y, PackedTangent.Z).GetSafeNormal();
            const FVector3f Along = Vertices.VertexTangentY(Vertex).GetSafeNormal();
            const int32 Axis = Along.Y > .99f ? 1 : Along.Z > .99f ? 2 : INDEX_NONE;
            // End-grain caps have a cross-piece bitangent; their hard seam is
            // intentional and must not be confused with an arc discontinuity.
            if (Axis == INDEX_NONE || FMath::Abs(Normal[Axis]) > .01f) continue;
            FSharedCorner& Shared = (Axis == 1 ? AlongY : AlongZ).FindOrAdd(PositionKey(Positions.VertexPosition(Vertex)));
            if (Shared.Count == 0)
            {
                Shared.Normal = Normal;
                Shared.Tangent = Tangent;
            }
            else
                bContinuous &= FVector3f::DotProduct(Shared.Normal, Normal) > .9999f
                    && FVector3f::DotProduct(Shared.Tangent, Tangent) > .9999f;
            ++Shared.Count;
            Shared.bCurved |= FMath::Abs(Normal[(Axis + 1) % 3]) > .1f
                && FMath::Abs(Normal[(Axis + 2) % 3]) > .1f;
        }
        int32 CurvedSharedPositions = 0;
        for (const auto* SharedPositions : {&AlongY, &AlongZ})
            for (const auto& Entry : *SharedPositions)
                CurvedSharedPositions += Entry.Value.bCurved && Entry.Value.Count > 1 ? 1 : 0;
        TestTrue(TEXT("Rounded profiles have shared intermediate arc corners"), CurvedSharedPositions > 0);
        TestTrue(TEXT("Rounded strips share continuous normals and tangents at coincident corners"), bContinuous);

        TMap<FIntVector, uint32> WeldedVertices;
        TMap<uint64, int32> EdgeCounts;
        const FIndexArrayView Indices = LOD.IndexBuffer.GetArrayView();
        for (int32 Index = 0; Index + 2 < Indices.Num(); Index += 3)
        {
            uint32 Triangle[3];
            for (int32 Corner = 0; Corner < 3; ++Corner)
            {
                const FIntVector Key = PositionKey(Positions.VertexPosition(Indices[Index + Corner]));
                const uint32 NewIndex = WeldedVertices.Num();
                Triangle[Corner] = WeldedVertices.FindOrAdd(Key, NewIndex);
            }
            for (int32 Corner = 0; Corner < 3; ++Corner)
            {
                const uint32 A = Triangle[Corner], B = Triangle[(Corner + 1) % 3];
                const uint64 Key = (uint64(FMath::Min(A, B)) << 32) | FMath::Max(A, B);
                ++EdgeCounts.FindOrAdd(Key);
            }
        }
        bool bClosed = !EdgeCounts.IsEmpty();
        for (const auto& Edge : EdgeCounts) bClosed &= Edge.Value == 2;
        TestTrue(TEXT("Every rounded extrusion remains closed after welding render seams"), bClosed);
    };
    auto CheckDepth = [&]()
    {
        const FBoxSphereBounds Bounds = Component->GetStaticMesh()->GetBounds();
        TestTrue(TEXT("All joinery stays in front of the camera"), Bounds.Origin.X - Bounds.BoxExtent.X > 0);
        TestTrue(TEXT("All joinery stays before the 100 cm precipitation fade"), Bounds.Origin.X + Bounds.BoxExtent.X < 100);
        const FBoxSphereBounds GlassBounds = RainGlass->GetStaticMesh()->GetBounds();
        TestTrue(TEXT("Glass lies behind every opaque frame profile"), GlassBounds.Origin.X - GlassBounds.BoxExtent.X > Bounds.Origin.X + Bounds.BoxExtent.X);
        TestTrue(TEXT("Glass stays at 96 cm before the precipitation fade"), FMath::IsNearlyEqual(GlassBounds.Origin.X, 96., .001)
            && GlassBounds.Origin.X + GlassBounds.BoxExtent.X < 100);
        TestTrue(TEXT("Glass overlaps the opening beneath the opaque profiles"), GlassBounds.BoxExtent.Y * 2 > Frame->GetOpeningSize().X
            && GlassBounds.BoxExtent.Z * 2 > Frame->GetOpeningSize().Y);
    };
    CheckDepth();
    CheckWinding();
    CheckRoundedProfiles();
    UStaticMesh* WideMesh = Component->GetStaticMesh();
    UStaticMesh* WideGlassMesh = RainGlass->GetStaticMesh();
    const FBoxSphereBounds WideGlassBounds = WideGlassMesh->GetBounds();
    Fit(16.f / 9.f);
    TestTrue(TEXT("Unchanged projection reuses its mesh"), Component->GetStaticMesh() == WideMesh);
    TestTrue(TEXT("Unchanged projection reuses its glass mesh"), RainGlass->GetStaticMesh() == WideGlassMesh);

    UMaterialInstanceDynamic* RainMaterial = Cast<UMaterialInstanceDynamic>(RainGlass->GetMaterial(0));
    if (!TestNotNull(TEXT("Rain glass uses a dynamic material"), RainMaterial))
    {
        World->DestroyWorld(false);
        return false;
    }
    TestEqual(TEXT("Rain starts at zero"), Frame->GetRainIntensity(), 0.f);
    TestFalse(TEXT("Clear weather omits the rain glass pass"), RainGlass->IsVisible());
    auto CheckRain = [&](float Requested, float Expected)
    {
        Frame->SetRainIntensity(Requested);
        TestEqual(TEXT("Rain intensity is sanitized"), Frame->GetRainIntensity(), Expected);
        TestEqual(TEXT("Rain material receives sanitized intensity"), RainMaterial->K2_GetScalarParameterValue(TEXT("RainIntensity")), Expected);
        TestEqual(TEXT("Only rain shows the glass effect"), RainGlass->IsVisible(), Expected > 0);
        TestTrue(TEXT("Weather changes preserve both meshes"), Component->GetStaticMesh() == WideMesh && RainGlass->GetStaticMesh() == WideGlassMesh);
        TestTrue(TEXT("Weather changes preserve the rain material instance"), RainGlass->GetMaterial(0) == RainMaterial);
        TestTrue(TEXT("Frame remains ready in clear and rainy weather"), Frame->IsReady());
    };
    CheckRain(.4f, .4f);
    CheckRain(2.f, 1.f);
    CheckRain(-.5f, 0.f);
    CheckRain(std::numeric_limits<float>::quiet_NaN(), 0.f);
    CheckRain(.6f, .6f);

    UMaterialInstanceDynamic* Finish = Cast<UMaterialInstanceDynamic>(Component->GetMaterial(0));
    if (!TestNotNull(TEXT("Frame finish is a dynamic material"), Finish))
    {
        World->DestroyWorld(false);
        return false;
    }
    TestEqual(TEXT("Default frame finish is graphite"), Frame->GetStyle(), FName(TEXT("graphite")));
    TestEqual(TEXT("Default finish has no timber grain"), Finish->K2_GetScalarParameterValue(TEXT("Grain")), 0.f);
    TestEqual(TEXT("Default powder coating is dielectric"), Finish->K2_GetScalarParameterValue(TEXT("Metallic")), 0.f);
    TestTrue(TEXT("Oak finish is accepted"), Frame->SetStyle(TEXT("oak")));
    const FLinearColor OakColor = Finish->K2_GetVectorParameterValue(TEXT("Color"));
    TestTrue(TEXT("Ivory finish is accepted"), Frame->SetStyle(TEXT("ivory")));
    TestEqual(TEXT("Ivory selection is retained"), Frame->GetStyle(), FName(TEXT("ivory")));
    TestFalse(TEXT("Ivory changes the finish color"), Finish->K2_GetVectorParameterValue(TEXT("Color")).Equals(OakColor));
    TestEqual(TEXT("Ivory paint has no timber grain"), Finish->K2_GetScalarParameterValue(TEXT("Grain")), 0.f);
    TestEqual(TEXT("Paint remains nonmetallic"), Finish->K2_GetScalarParameterValue(TEXT("Metallic")), 0.f);
    TestTrue(TEXT("Changing to ivory reuses geometry"), Component->GetStaticMesh() == WideMesh);
    TestTrue(TEXT("Graphite finish is accepted"), Frame->SetStyle(TEXT("graphite")));
    TestEqual(TEXT("Graphite removes timber grain"), Finish->K2_GetScalarParameterValue(TEXT("Grain")), 0.f);
    TestEqual(TEXT("Graphite uses a dielectric powder coat"), Finish->K2_GetScalarParameterValue(TEXT("Metallic")), 0.f);
    const FLinearColor GraphiteColor = Finish->K2_GetVectorParameterValue(TEXT("Color"));
    TestFalse(TEXT("Unknown finish is rejected"), Frame->SetStyle(TEXT("unknown")));
    TestEqual(TEXT("Unknown finish preserves selection"), Frame->GetStyle(), FName(TEXT("graphite")));
    TestTrue(TEXT("Unknown finish preserves color"), Finish->K2_GetVectorParameterValue(TEXT("Color")).Equals(GraphiteColor));
    TestEqual(TEXT("Unknown finish preserves metalness"), Finish->K2_GetScalarParameterValue(TEXT("Metallic")), 0.f);
    TestTrue(TEXT("Returning to oak is accepted"), Frame->SetStyle(TEXT("oak")));
    TestTrue(TEXT("Returning to oak restores its color"), Finish->K2_GetVectorParameterValue(TEXT("Color")).Equals(OakColor));
    TestEqual(TEXT("Returning to oak restores its grain"), Finish->K2_GetScalarParameterValue(TEXT("Grain")), 1.f);
    TestEqual(TEXT("Returning to oak removes metalness"), Finish->K2_GetScalarParameterValue(TEXT("Metallic")), 0.f);
    TestTrue(TEXT("Style changes preserve the material instance"), Component->GetMaterial(0) == Finish);
    TestTrue(TEXT("Style changes preserve geometry"), Component->GetStaticMesh() == WideMesh);
    TestEqual(TEXT("Style changes preserve triangle count"), Frame->GetTriangleCount(), Triangles);
    TestTrue(TEXT("Style changes preserve rain glass and its material"), RainGlass->GetStaticMesh() == WideGlassMesh && RainGlass->GetMaterial(0) == RainMaterial);
    TestTrue(TEXT("Style changes leave rain visible"), RainGlass->IsVisible());
    TestEqual(TEXT("Style changes retain rain intensity"), RainMaterial->K2_GetScalarParameterValue(TEXT("RainIntensity")), .6f);

    Fit(3.f / 4.f);
    TestTrue(TEXT("Narrow window rebuild remains ready"), Frame->IsReady());
    const FVector2D NarrowOpening = Frame->GetOpeningSize();
    TestTrue(TEXT("Narrow viewport reduces opening width"), NarrowOpening.X > 0 && NarrowOpening.X < WideOpening.X);
    TestTrue(TEXT("Fixed vertical FOV preserves opening height"), FMath::IsNearlyEqual(NarrowOpening.Y, WideOpening.Y, .001));
    TestEqual(TEXT("Resizing preserves joinery topology"), Frame->GetTriangleCount(), Triangles);
    const FBoxSphereBounds NarrowGlassBounds = RainGlass->GetStaticMesh()->GetBounds();
    TestTrue(TEXT("Narrow viewport reduces glass width"), NarrowGlassBounds.BoxExtent.Y < WideGlassBounds.BoxExtent.Y);
    TestTrue(TEXT("Fixed vertical FOV preserves glass height"), FMath::IsNearlyEqual(NarrowGlassBounds.BoxExtent.Z, WideGlassBounds.BoxExtent.Z, .001));
    TestTrue(TEXT("Projection changes preserve the rain material and visibility"), RainGlass->GetMaterial(0) == RainMaterial && RainGlass->IsVisible());
    TestEqual(TEXT("Projection changes preserve rain intensity"), RainMaterial->K2_GetScalarParameterValue(TEXT("RainIntensity")), .6f);
    CheckDepth();
    CheckWinding();
    CheckRoundedProfiles();

    CheckRoom();
    Frame->SetDaylight(1);
    TestEqual(TEXT("Daytime frame receives no artificial room fill"), RoomBounce->Intensity, 0.f);
    Frame->SetDaylight(.5f);
    TestEqual(TEXT("Overcast daylight does not turn on the indoor lamp"), RoomBounce->Intensity, 0.f);
    Frame->SetDaylight(0);
    const float NightRoomIntensity = RoomBounce->Intensity;
    TestTrue(TEXT("The room stays lit at night"), RoomBounce->IsVisible() && NightRoomIntensity > 0);
    Frame->SetDaylight(.1f);
    TestEqual(TEXT("Late twilight uses the full indoor lamp"), RoomBounce->Intensity, NightRoomIntensity);
    Frame->SetDaylight(.3f);
    TestTrue(TEXT("Indoor lamp fades smoothly through twilight"), RoomBounce->Intensity > 0 && RoomBounce->Intensity < NightRoomIntensity);
    if (IConsoleVariable* Lumens = IConsoleManager::Get().FindConsoleVariable(TEXT("oow.FrameRoomLumens")))
    {
        const float OriginalLumens = Lumens->GetFloat();
        Lumens->SetWithCurrentPriority(60.f);
        Frame->SetDaylight(0);
        TestEqual(TEXT("Indoor lamp brightness remains calibratable"), RoomBounce->Intensity, 60.f);
        Lumens->SetWithCurrentPriority(OriginalLumens);
    }
    else AddError(TEXT("Indoor lamp calibration console variable is missing"));
    Frame->SetDaylight(0);
    TestTrue(TEXT("Night uses a warm-white native light temperature"), RoomBounce->bUseTemperature
        && RoomBounce->Temperature >= 3000.f && RoomBounce->Temperature <= 4000.f);
    const bool bOriginalScreenMessages = GAreScreenMessagesEnabled;
    const TSharedRef<SWindowVisibilityButton> Eye = SNew(SWindowVisibilityButton);
    UStaticMesh* NarrowMesh = Component->GetStaticMesh();
    UStaticMesh* NarrowGlassMesh = RainGlass->GetStaticMesh();
    Eye->SetInterfaceHidden(true);
    TestTrue(TEXT("UI is hidden"), Eye->IsInterfaceHidden());
    TestTrue(TEXT("Hidden UI leaves the physical frame ready"), Frame->IsReady());
    TestTrue(TEXT("Hidden UI leaves the frame visible"), Component->IsVisible() && !Frame->IsHidden());
    TestTrue(TEXT("Hidden UI leaves frame geometry intact"), Component->GetStaticMesh() == NarrowMesh);
    TestEqual(TEXT("Hidden UI preserves triangle count"), Frame->GetTriangleCount(), Triangles);
    TestTrue(TEXT("Hidden UI leaves rain glass visible"), RainGlass->IsVisible());
    TestTrue(TEXT("Hidden UI leaves rain glass geometry and material intact"), RainGlass->GetStaticMesh() == NarrowGlassMesh && RainGlass->GetMaterial(0) == RainMaterial);
    TestEqual(TEXT("Hidden UI preserves rain intensity"), RainMaterial->K2_GetScalarParameterValue(TEXT("RainIntensity")), .6f);
    TestTrue(TEXT("Hidden UI leaves the indoor light visible"), RoomBounce->IsVisible());
    TestEqual(TEXT("Hidden UI preserves indoor light intensity"), RoomBounce->Intensity, NightRoomIntensity);
    Eye->SetInterfaceHidden(false);
    TestFalse(TEXT("UI can be restored"), Eye->IsInterfaceHidden());
    TestEqual(TEXT("Restoring UI restores screen message state"), GAreScreenMessagesEnabled, bOriginalScreenMessages);
    TestTrue(TEXT("Restored UI leaves the physical frame ready"), Frame->IsReady());
    TestTrue(TEXT("Restoring UI leaves rain glass visible"), RainGlass->IsVisible());
    TestTrue(TEXT("Restoring UI leaves the indoor light visible"), RoomBounce->IsVisible());
    TestEqual(TEXT("Restoring UI preserves indoor light intensity"), RoomBounce->Intensity, NightRoomIntensity);

    Frame->SetRainIntensity(0);
    TestFalse(TEXT("Returning to clear weather hides the rain effect"), RainGlass->IsVisible());
    TestTrue(TEXT("Clear weather retains the glass mesh and material"), RainGlass->GetStaticMesh() == NarrowGlassMesh && RainGlass->GetMaterial(0) == RainMaterial);
    TestEqual(TEXT("Clear weather clears the shader rain intensity"), RainMaterial->K2_GetScalarParameterValue(TEXT("RainIntensity")), 0.f);

    Fit(16.f / 9.f);
    TestTrue(TEXT("Returning to landscape restores opening dimensions"), Frame->GetOpeningSize().Equals(WideOpening, .001));
    TestEqual(TEXT("Repeated resizing preserves triangle count"), Frame->GetTriangleCount(), Triangles);
    TestTrue(TEXT("Returning to landscape restores glass dimensions"), RainGlass->GetStaticMesh()->GetBounds().BoxExtent.Equals(WideGlassBounds.BoxExtent, .001));
    TestFalse(TEXT("Resizing in clear weather does not show rain glass"), RainGlass->IsVisible());
    TestTrue(TEXT("Repeated resizing preserves the rain material"), RainGlass->GetMaterial(0) == RainMaterial);
    TestTrue(TEXT("Frame remains ready after resizing and UI toggles"), Frame->IsReady());
    CheckRoom();
    CheckWinding();
    CheckRoundedProfiles();
    World->DestroyWorld(false);
    return true;
}

#endif
