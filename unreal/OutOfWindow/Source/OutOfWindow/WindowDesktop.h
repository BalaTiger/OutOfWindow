#pragma once

#include "CoreMinimal.h"

class AWindowDirector;

// Owns only the standalone game's native window. PIE and editor windows are excluded.
class FWindowDesktop
{
public:
	static void InitializeProcess();
	static void ShutdownProcess();
	FWindowDesktop();
	~FWindowDesktop();
	void Initialize(AWindowDirector* Director);
	void Tick();
	void Shutdown();

private:
	struct FImpl;
	TUniquePtr<FImpl> Impl;
};
