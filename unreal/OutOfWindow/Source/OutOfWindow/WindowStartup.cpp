#include "WindowStartup.h"
#include "WindowDirector.h"
#include "Dom/JsonObject.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LevelStreaming.h"
#include "Engine/World.h"
#include "Framework/Application/SlateApplication.h"
#include "GenericPlatform/GenericApplication.h"
#include "GenericPlatform/GenericWindow.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "Misc/CommandLine.h"
#include "Misc/CoreDelegates.h"
#include "Misc/CoreMisc.h"
#include "Misc/FileHelper.h"
#include "Misc/Guid.h"
#include "Misc/Paths.h"
#include "Misc/OutputDeviceRedirector.h"
#include "PipelineStateCache.h"
#include "RenderingThread.h"
#include "RHICommandList.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/UObjectGlobals.h"
#include "UnrealClient.h"
#include "Widgets/SWindow.h"
#include <atomic>
#if WITH_EDITOR
#include "AssetCompilingManager.h"
#include "ShaderCompiler.h"
#endif
#if PLATFORM_WINDOWS
#include "Windows/WindowsHWrapper.h"
#include "Windows/AllowWindowsPlatformTypes.h"
#include <dwmapi.h>
#include "Windows/HideWindowsPlatformTypes.h"
#endif

DEFINE_LOG_CATEGORY_STATIC(LogWindowStartup, Log, All);

namespace
{
struct FFrameCompletion
{
	FGPUFenceRHIRef Fence;
	std::atomic<bool> Complete{false};
	bool bCompletionLogged = false; // Only read and written by the render thread.
	FIntPoint RenderSize = FIntPoint::ZeroValue;
};
struct FStartupSession
{
	FString Id, StatusPath;
	int32 Sequence = 0;
	bool bActive = false, bFinished = false, bFailed = false, bDesktopAttached = false;
	TWeakObjectPtr<AWindowDirector> Director;
	TWeakObjectPtr<UGameViewportClient> Viewport;
	FDelegateHandle DrawHandle, MapHandle, EndFrameHandle;
	TSharedPtr<FFrameCompletion, ESPMode::ThreadSafe> Frame;
	double FrameStartedAt = 0;
	double StartedAt = FPlatformTime::Seconds(), SceneReadyAt = 0;
	uint64 RenderAfterFrame = 0;
#if PLATFORM_WINDOWS
	HHOOK ShowHook = nullptr;
	HWND Window = nullptr;
#endif
};
FStartupSession Startup;

#if PLATFORM_WINDOWS
void LogNativeState(const TCHAR* Event)
{
	DWORD Cloaked = 0;
	const HRESULT ReadResult = DwmGetWindowAttribute(Startup.Window, DWMWA_CLOAKED, &Cloaked, sizeof(Cloaked));
	UE_LOG(LogWindowStartup, Display, TEXT("OOW_STARTUP_BOUNDARY session=%s pid=%u event=%s hwnd=%p visible=%d cloaked=%u query=0x%08x elapsed=%.3f finished=%d failed=%d"),
		*Startup.Id, FPlatformProcess::GetCurrentProcessId(), Event, static_cast<void*>(Startup.Window), IsWindowVisible(Startup.Window) != 0,
		static_cast<uint32>(Cloaked), static_cast<uint32>(ReadResult), FPlatformTime::Seconds() - Startup.StartedAt, Startup.bFinished, Startup.bFailed);
}
#endif

bool SceneReady()
{
	const AWindowDirector* Director = Startup.Director.Get();
	UWorld* World = Director ? Director->GetWorld() : nullptr;
	UGameViewportClient* Viewport = Startup.Viewport.Get();
	if (!World || World->WorldType != EWorldType::Game || !Director->IsStartupSceneReady()
		|| !World->HasBegunPlay() || !World->AreActorsInitialized() || IsAsyncLoading()) return false;
	if (!Viewport || Viewport->bDisableWorldRendering || !FViewport::IsGameRenderingEnabled()
		|| !FSlateApplication::IsInitialized() || !FSlateApplication::Get().GetPlatformApplication()->IsAllowedToRender()) return false;
	if (PipelineStateCache::IsPrecaching() || PipelineStateCache::GetNumActivePipelinePrecompileTasks() > 0) return false;
	for (ULevelStreaming* Level : World->GetStreamingLevels())
		if (Level && (Level->IsStreamingStatePending()
			|| (Level->ShouldBeLoaded() && !Level->IsLevelLoaded())
			|| (Level->ShouldBeVisible() && !Level->IsLevelVisible()))) return false;
#if WITH_EDITOR
	if ((GShaderCompilingManager && GShaderCompilingManager->IsCompiling())
		|| FAssetCompilingManager::Get().GetNumRemainingAssets() > 0) return false;
#endif
	return true;
}

void StopObserving()
{
	if (UGameViewportClient* Viewport = Startup.Viewport.Get()) Viewport->OnEndDraw().Remove(Startup.DrawHandle);
	Startup.Viewport.Reset();
	FCoreUObjectDelegates::PreLoadMap.Remove(Startup.MapHandle);
	FCoreDelegates::OnEndFrame.Remove(Startup.EndFrameHandle);
#if PLATFORM_WINDOWS
	if (Startup.ShowHook) UnhookWindowsHookEx(Startup.ShowHook);
	Startup.ShowHook = nullptr;
#endif
}

bool Reveal()
{
#if PLATFORM_WINDOWS
	if (IsWindow(Startup.Window))
	{
		LogNativeState(TEXT("reveal_before"));
		const BOOL Cloak = 0;
		const HRESULT Result = DwmSetWindowAttribute(Startup.Window, DWMWA_CLOAK, &Cloak, sizeof(Cloak));
		DWORD State = DWM_CLOAKED_APP;
		const HRESULT ReadResult = DwmGetWindowAttribute(Startup.Window, DWMWA_CLOAKED, &State, sizeof(State));
		LogNativeState(TEXT("reveal_after"));
		if (FAILED(Result) || FAILED(ReadResult) || (State & DWM_CLOAKED_APP))
		{
			UE_LOG(LogWindowStartup, Error, TEXT("Cannot remove startup window cloak: 0x%08x"), static_cast<uint32>(Result));
			return false;
		}
		return true;
	}
#endif
	return true;
}

#if PLATFORM_WINDOWS
LRESULT CALLBACK BeforeShow(int Code, WPARAM WParam, LPARAM LParam)
{
	if (Code >= 0 && FWindowStartup::IsPending() && !Startup.Window)
	{
		const CWPSTRUCT* Message = reinterpret_cast<CWPSTRUCT*>(LParam);
		const bool bShowing = (Message->message == WM_SHOWWINDOW && Message->wParam)
			|| (Message->message == WM_WINDOWPOSCHANGING
				&& (reinterpret_cast<WINDOWPOS*>(Message->lParam)->flags & SWP_SHOWWINDOW));
		if (bShowing && !(GetWindowLongPtrW(Message->hwnd, GWL_STYLE) & WS_CHILD))
		{
			WCHAR Class[64] = {};
			DWORD Process = 0;
			GetClassNameW(Message->hwnd, Class, UE_ARRAY_COUNT(Class));
			GetWindowThreadProcessId(Message->hwnd, &Process);
			if (Process == GetCurrentProcessId() && !wcscmp(Class, L"UnrealWindow"))
			{
				const BOOL Cloak = 1;
				Startup.Window = Message->hwnd;
				const HRESULT Result = DwmSetWindowAttribute(Startup.Window, DWMWA_CLOAK, &Cloak, sizeof(Cloak));
				DWORD State = 0;
				const HRESULT ReadResult = DwmGetWindowAttribute(Startup.Window, DWMWA_CLOAKED, &State, sizeof(State));
				if (FAILED(Result) || FAILED(ReadResult) || !(State & DWM_CLOAKED_APP))
					FWindowStartup::Fail(FString::Printf(TEXT("无法遮挡启动画面（0x%08x）；正在尝试显示游戏窗口。请查看日志，可在启动器中取消或重试。"), static_cast<uint32>(FAILED(Result) ? Result : ReadResult)));
				else LogNativeState(TEXT("cloak_before_show_dispatch"));
			}
		}
	}
	return CallNextHookEx(nullptr, Code, WParam, LParam);
}
#endif

void OnViewportDrawn()
{
	if (!FWindowStartup::IsPending() || Startup.Frame || GFrameCounter < Startup.RenderAfterFrame || !SceneReady()) return;
	Startup.Frame = MakeShared<FFrameCompletion, ESPMode::ThreadSafe>();
	if (Startup.Viewport.IsValid() && Startup.Viewport->Viewport) Startup.Frame->RenderSize = Startup.Viewport->Viewport->GetSizeXY();
	Startup.FrameStartedAt = FPlatformTime::Seconds();
	const auto Frame = Startup.Frame;
	// This marker follows this viewport's draw commands, rather than counting game ticks.
	ENQUEUE_RENDER_COMMAND(OOWStartupFrame)([Frame](FRHICommandListImmediate& RHICmdList)
	{
		Frame->Fence = RHICreateGPUFence(TEXT("OOWStartupFrame"));
		RHICmdList.WriteGPUFence(Frame->Fence);
	});
}

void PollFrame()
{
	if (!FWindowStartup::IsPending()) return;
	if (!Startup.Viewport.IsValid() && FPlatformTime::Seconds() - Startup.StartedAt > 120)
	{
		FWindowStartup::Fail(TEXT("仍无法确认场景视口，正在尝试显示游戏窗口；这不代表进程崩溃。请查看日志，可在启动器中取消或重试。"));
		return;
	}
	if (!Startup.Frame)
	{
		if (Startup.SceneReadyAt > 0 && FPlatformTime::Seconds() - Startup.SceneReadyAt > 60)
			FWindowStartup::Fail(TEXT("场景已初始化，但尚未观察到视口绘制；正在尝试恢复游戏窗口。请查看日志，可在启动器中取消或重试。"));
		return;
	}
	const auto Frame = Startup.Frame;
	if (!Frame->Complete.load())
	{
		const FString Session = Startup.Id;
		const bool bDesktopFrame = Startup.bDesktopAttached;
		ENQUEUE_RENDER_COMMAND(OOWPollStartupFrame)([Frame, Session, bDesktopFrame](FRHICommandListImmediate&)
		{
			if (Frame->Fence && Frame->Fence->Poll())
			{
				if (!Frame->bCompletionLogged)
				{
					Frame->bCompletionLogged = true;
					UE_LOG(LogWindowStartup, Display, TEXT("OOW_STARTUP_BOUNDARY session=%s pid=%u event=%s width=%d height=%d"),
						*Session, FPlatformProcess::GetCurrentProcessId(), bDesktopFrame ? TEXT("desktop_gpu_frame_complete") : TEXT("scene_gpu_frame_complete"),
						Frame->RenderSize.X, Frame->RenderSize.Y);
				}
				Frame->Complete.store(true);
			}
		});
		if (FPlatformTime::Seconds() - Startup.FrameStartedAt > 60)
			FWindowStartup::Fail(TEXT("场景帧提交后等待超过 60 秒仍未完成；正在尝试恢复游戏窗口。请查看渲染日志，可在启动器中取消或重试。"));
	}
}
}

void FWindowStartup::Report(const TCHAR* Stage, const FString& Detail)
{
	if (!Startup.bActive) return;
	TSharedRef<FJsonObject> Status = MakeShared<FJsonObject>();
	Status->SetNumberField(TEXT("version"), 1);
	Status->SetStringField(TEXT("session"), Startup.Id);
	Status->SetNumberField(TEXT("pid"), FPlatformProcess::GetCurrentProcessId());
	Status->SetNumberField(TEXT("sequence"), ++Startup.Sequence);
	Status->SetStringField(TEXT("utc"), FDateTime::UtcNow().ToIso8601());
	Status->SetStringField(TEXT("stage"), Stage);
	Status->SetStringField(TEXT("detail"), Detail);
	FString Json;
	FJsonSerializer::Serialize(Status, TJsonWriterFactory<>::Create(&Json));
	const FString Temporary = Startup.StatusPath + TEXT(".tmp");
	const bool bWritten = FFileHelper::SaveStringToFile(Json, *Temporary, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
#if PLATFORM_WINDOWS
	const DWORD WriteError = bWritten ? 0 : GetLastError();
	DWORD FirstMoveError = 0, LastMoveError = 0;
	int32 PublishAttempts = 0;
	bool bPublished = false;
	if (bWritten)
	{
		for (int32 Attempt = 0; Attempt <= 10; ++Attempt)
		{
			++PublishAttempts;
			if (MoveFileExW(*Temporary, *Startup.StatusPath, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
			{
				bPublished = true;
				LastMoveError = 0;
				break;
			}
			LastMoveError = GetLastError();
			if (Attempt == 0) FirstMoveError = LastMoveError;
			if (Attempt == 10 || (LastMoveError != ERROR_SHARING_VIOLATION && LastMoveError != ERROR_ACCESS_DENIED)) break;
			FPlatformProcess::SleepNoStats(.02f);
		}
	}
	if (bPublished && FirstMoveError != 0)
		UE_LOG(LogWindowStartup, Warning, TEXT("OOW_STARTUP_PUBLISH_RETRY session=%s pid=%u written=%d published=%d firstMoveError=%u lastMoveError=%u attempts=%d"),
			*Startup.Id, FPlatformProcess::GetCurrentProcessId(), bWritten, bPublished,
			static_cast<uint32>(FirstMoveError), static_cast<uint32>(LastMoveError), PublishAttempts);
#else
	const bool bPublished = bWritten && IFileManager::Get().Move(*Startup.StatusPath, *Temporary, true, true);
#endif
	UE_LOG(LogWindowStartup, Display, TEXT("OOW_STARTUP session=%s pid=%u stage=%s detail=%s"), *Startup.Id, FPlatformProcess::GetCurrentProcessId(), Stage, *Detail);
	if (!bPublished)
	{
#if PLATFORM_WINDOWS
		UE_LOG(LogWindowStartup, Error, TEXT("OOW_STARTUP_PUBLISH_FAILED session=%s pid=%u written=%d published=%d writeError=%u firstMoveError=%u lastMoveError=%u attempts=%d"),
			*Startup.Id, FPlatformProcess::GetCurrentProcessId(), bWritten, bPublished,
			static_cast<uint32>(WriteError), static_cast<uint32>(FirstMoveError), static_cast<uint32>(LastMoveError), PublishAttempts);
#endif
		UE_LOG(LogWindowStartup, Error, TEXT("OOW_STARTUP_ERROR session=%s pid=%u detail=无法发布启动状态，正在尝试恢复游戏窗口；请查看日志，可在启动器中取消或重试。状态路径：%s"), *Startup.Id, FPlatformProcess::GetCurrentProcessId(), *Startup.StatusPath);
		Startup.bFailed = true;
		if (GLog) GLog->Flush(); // Publish the exceptional log fallback without flushing every normal engine message.
		StopObserving();
		Reveal();
	}
}

void FWindowStartup::Initialize()
{
	if ((GIsEditor && !FParse::Param(FCommandLine::Get(), TEXT("game"))) || IsRunningCommandlet() || IsRunningDedicatedServer()) return;
	FString Id, Path, Capture;
	FGuid Guid;
	if (!FParse::Value(FCommandLine::Get(), TEXT("OOWLaunchId="), Id)
		|| !FGuid::Parse(Id, Guid) || !FParse::Value(FCommandLine::Get(), TEXT("OOWLaunchStatus="), Path)
		|| FPaths::IsRelative(Path) || FParse::Value(FCommandLine::Get(), TEXT("OOWCapture="), Capture)) return;
	Startup.Id = Id;
	Startup.StatusPath = FPaths::ConvertRelativePathToFull(Path);
	Startup.bActive = true;
	Report(TEXT("renderer"), TEXT("渲染器进程已启动，正在初始化。"));
	if (!IsPending()) return;
#if PLATFORM_WINDOWS
	Startup.ShowHook = SetWindowsHookExW(WH_CALLWNDPROC, BeforeShow, nullptr, GetCurrentThreadId());
	if (!Startup.ShowHook)
	{
		Fail(TEXT("无法安装启动窗口保护；正在尝试显示游戏窗口。请查看日志，可在启动器中取消或重试。"));
		return;
	}
#endif
	Startup.MapHandle = FCoreUObjectDelegates::PreLoadMap.AddLambda([](const FString& Map)
	{
		if (FWindowStartup::IsPending()) FWindowStartup::Report(TEXT("scene"), TEXT("正在加载场景：") + Map);
	});
	Startup.EndFrameHandle = FCoreDelegates::OnEndFrame.AddStatic(&PollFrame);
}

bool FWindowStartup::IsActive() { return Startup.bActive; }
bool FWindowStartup::HasFailed() { return Startup.bFailed; }
bool FWindowStartup::IsPending() { return Startup.bActive && !Startup.bFinished && !Startup.bFailed; }

bool FWindowStartup::WaitForSceneFrame(AWindowDirector* Director)
{
	if (!IsPending()) return true;
	if (!Director || !Director->GetWorld()) return false;
	if (!Director->GetStartupSceneError().IsEmpty())
	{
		Fail(TEXT("场景初始化缺少必要对象：") + Director->GetStartupSceneError());
		return false;
	}
	Startup.Director = Director;
	UGameViewportClient* Viewport = Director->GetWorld()->GetGameViewport();
	if (Viewport != Startup.Viewport.Get())
	{
		if (UGameViewportClient* Old = Startup.Viewport.Get()) Old->OnEndDraw().Remove(Startup.DrawHandle);
		Startup.Viewport = Viewport;
		Startup.Frame.Reset();
		if (Viewport) Startup.DrawHandle = Viewport->OnEndDraw().AddStatic(&OnViewportDrawn);
	}
	if (!SceneReady())
	{
		Startup.Frame.Reset();
		Startup.SceneReadyAt = 0;
		return false;
	}
	if (Startup.SceneReadyAt == 0) Startup.SceneReadyAt = FPlatformTime::Seconds();
#if PLATFORM_WINDOWS
	const auto Window = Viewport ? Viewport->GetWindow() : nullptr;
	if (!Window || !Window->GetNativeWindow()) return false;
	if (Startup.Window != Window->GetNativeWindow()->GetOSWindowHandle())
	{
		const HWND NativeWindow = static_cast<HWND>(Window->GetNativeWindow()->GetOSWindowHandle());
		DWORD Process = 0;
		GetWindowThreadProcessId(NativeWindow, &Process);
		if (Process == GetCurrentProcessId())
		{
			Reveal();
			Startup.Window = NativeWindow;
		}
		Fail(TEXT("未能确认视口的启动保护；正在尝试显示游戏窗口。请查看日志，可在启动器中取消或重试。"));
		return false;
	}
#endif
	return Startup.Frame && Startup.Frame->Complete.load();
}

bool FWindowStartup::DesktopAttached()
{
	if (!IsPending()) return !HasFailed();
#if PLATFORM_WINDOWS
	DWORD State = 0;
	if (FAILED(DwmGetWindowAttribute(Startup.Window, DWMWA_CLOAKED, &State, sizeof(State))) || !(State & DWM_CLOAKED_APP))
	{
		Fail(TEXT("桌面挂接后无法确认窗口遮挡；正在尝试恢复普通窗口。请查看日志，可在启动器中取消或重试。"));
		return false;
	}
	ShowWindow(Startup.Window, SW_SHOWNA);
#endif
	Startup.bDesktopAttached = true;
	Startup.Frame.Reset();
	Startup.SceneReadyAt = FPlatformTime::Seconds();
	// Let the director update camera FOV for the new desktop dimensions before drawing.
	Startup.RenderAfterFrame = GFrameCounter + 1;
	Report(TEXT("desktop"), TEXT("桌面已连接，正在绘制桌面尺寸的场景。"));
	return !HasFailed();
}

void FWindowStartup::Finish()
{
	if (!IsPending() || !Startup.bDesktopAttached) return;
#if PLATFORM_WINDOWS
	if (!IsWindow(Startup.Window) || !IsWindowVisible(Startup.Window))
	{
		Fail(TEXT("桌面视口目前不可见，无法确认启动就绪；请查看日志或重试。"));
		return;
	}
#endif
	if (!Reveal())
	{
		Fail(TEXT("桌面已连接，但 Windows 无法显示游戏窗口；请在启动器中取消或重试。"));
		return;
	}
	Startup.bFinished = true;
	StopObserving();
	Report(TEXT("ready"), TEXT("场景已初始化并完成绘制，桌面连接成功。"));
	FString Capture;
	if (!HasFailed() && FParse::Value(FCommandLine::Get(), TEXT("OOWStartupCapture="), Capture)
		&& !FPaths::IsRelative(Capture) && FPaths::GetExtension(Capture).Equals(TEXT("png"), ESearchCase::IgnoreCase))
	{
		FScreenshotRequest::RequestScreenshot(Capture, true, false);
		UE_LOG(LogWindowStartup, Display, TEXT("OOW_STARTUP_CAPTURE_REQUEST session=%s pid=%u path=%s"),
			*Startup.Id, FPlatformProcess::GetCurrentProcessId(), *Capture);
	}
}

void FWindowStartup::Fail(const FString& Detail)
{
	if (!Startup.bActive || Startup.bFailed || Startup.bFinished) return;
	Startup.bFailed = true;
	StopObserving();
	Reveal();
#if PLATFORM_WINDOWS
	if (IsWindow(Startup.Window)) ShowWindow(Startup.Window, SW_SHOWNOACTIVATE);
#endif
	Report(TEXT("error"), Detail);
}

void FWindowStartup::Shutdown()
{
	StopObserving();
	Reveal();
	Startup.Frame.Reset();
}
