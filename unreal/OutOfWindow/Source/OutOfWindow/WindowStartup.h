#pragma once

#include "CoreMinimal.h"

class AWindowDirector;

// The launcher owns process lifetime; this class reports only this UE session.
class FWindowStartup
{
public:
	static void Initialize();
	static void Shutdown();
	static bool IsPending();
	static bool IsActive();
	static bool HasFailed();
	static bool WaitForSceneFrame(AWindowDirector* Director);
	static bool DesktopAttached();
	static void Finish();
	static void Fail(const FString& Detail);
	static void Report(const TCHAR* Stage, const FString& Detail);
};
