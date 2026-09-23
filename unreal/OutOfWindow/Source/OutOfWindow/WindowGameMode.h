#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "WindowGameMode.generated.h"

UCLASS()
class OUTOFWINDOW_API AWindowGameMode : public AGameModeBase
{
    GENERATED_BODY()

public:
    AWindowGameMode();
    virtual void BeginPlay() override;
};
