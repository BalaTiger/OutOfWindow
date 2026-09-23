#include "WindowGameMode.h"
#include "WindowDirector.h"
#include "EngineUtils.h"
#include "Engine/World.h"

AWindowGameMode::AWindowGameMode()
{
    DefaultPawnClass = nullptr;
    HUDClass = nullptr;
}

void AWindowGameMode::BeginPlay()
{
    Super::BeginPlay();
    for (TActorIterator<AWindowDirector> It(GetWorld()); It; ++It) return;
    GetWorld()->SpawnActor<AWindowDirector>();
}
