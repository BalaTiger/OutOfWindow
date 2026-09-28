#include "WindowMaterialLibrary.h"
#include "Materials/Material.h"

bool UWindowMaterialLibrary::EnableConnectedWorldPositionOffset(UMaterial* Material)
{
#if WITH_EDITOR
    if (Material)
    {
        auto& Input = Material->GetEditorOnlyData()->WorldPositionOffset;
        if (Input.Expression && Input.UseConstant)
        {
            // Match the material editor's root connection handling (UE-219232).
            // Python ConnectMaterialProperty leaves this unreflected flag intact.
            Input.UseConstant = false;
            return true;
        }
    }
#endif
    return false;
}
