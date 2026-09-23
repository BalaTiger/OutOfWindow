#include "Modules/ModuleManager.h"
#include "WindowDesktop.h"

class FOutOfWindowModule : public FDefaultGameModuleImpl
{
public:
    virtual void StartupModule() override { FWindowDesktop::InitializeProcess(); }
    virtual void ShutdownModule() override { FWindowDesktop::ShutdownProcess(); }
};

IMPLEMENT_PRIMARY_GAME_MODULE(FOutOfWindowModule, OutOfWindow, "OutOfWindow");
