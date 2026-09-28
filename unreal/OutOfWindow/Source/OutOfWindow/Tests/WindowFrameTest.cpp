#if WITH_DEV_AUTOMATION_TESTS

#include "../WindowFrame.h"
#include "../WindowVisibilityButton.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/RectLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
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
    TArray<UStaticMeshComponent*> MeshComponents;
    Frame->GetComponents(MeshComponents);
    for (UStaticMeshComponent* MeshComponent : MeshComponents)
        if (MeshComponent->GetFName() == TEXT("WindowRainGlass")) RainGlass = MeshComponent;
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
    TestTrue(TEXT("Room light illuminates only the dedicated indoor channel"), RoomBounce->LightingChannels.bChannel1
        && !RoomBounce->LightingChannels.bChannel0 && !RoomBounce->LightingChannels.bChannel2);
    TestTrue(TEXT("Frame receives the indoor light channel"), Component->LightingChannels.bChannel1);
    TestEqual(TEXT("Room light cannot brighten the outdoor indirect lighting"), RoomBounce->IndirectLightingIntensity, 0.f);
    TestEqual(TEXT("Room light cannot brighten outdoor volumetric fog"), RoomBounce->VolumetricScatteringIntensity, 0.f);
    TestFalse(TEXT("Room light cannot spill onto outdoor glass or precipitation"), RoomBounce->bAffectTranslucentLighting);
    TestTrue(TEXT("Frame follows the camera independently of world placement"), Component->GetAttachParent() == View);
    TestEqual(TEXT("Frame cannot collide with the scene"), Component->GetCollisionEnabled(), ECollisionEnabled::NoCollision);
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
                    if (!(FVector3f::DotProduct(FaceNormal, Normal) > .99f)) InvalidTriangle = Index / 3;
                }
                if (InvalidTriangle != INDEX_NONE) break;
            }
            TestTrue(FString::Printf(TEXT("%s rendered winding matches every stored normal (first invalid triangle: %d)"),
                *Part->GetName(), InvalidTriangle), InvalidTriangle == INDEX_NONE);
        }
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

    const float DayRoomIntensity = RoomBounce->Intensity;
    Frame->SetDaylight(0);
    const float NightRoomIntensity = RoomBounce->Intensity;
    TestTrue(TEXT("The room stays lit at night"), RoomBounce->IsVisible() && NightRoomIntensity > 0);
    TestTrue(TEXT("Daylight supplements the persistent indoor lamp"), DayRoomIntensity > NightRoomIntensity);
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
    CheckWinding();
    World->DestroyWorld(false);
    return true;
}

#endif
