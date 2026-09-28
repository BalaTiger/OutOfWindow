#pragma once

#include "Kismet/BlueprintFunctionLibrary.h"
#include "WindowMaterialLibrary.generated.h"

class UMaterial;

UCLASS()
class OUTOFWINDOW_API UWindowMaterialLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    /** Allow a connected WPO expression to override an imported constant value. */
    UFUNCTION(BlueprintCallable, Category = "OutOfWindow|Materials")
    static bool EnableConnectedWorldPositionOffset(UMaterial* Material);
};
