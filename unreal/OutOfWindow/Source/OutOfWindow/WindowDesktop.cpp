#include "WindowDesktop.h"
#include "WindowDirector.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Framework/Application/SlateApplication.h"
#include "GenericPlatform/GenericWindow.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformTime.h"
#include "Misc/CommandLine.h"
#include "Misc/CoreMisc.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Widgets/SWindow.h"

#if PLATFORM_WINDOWS
#include "Windows/WindowsHWrapper.h"
#include "Windows/AllowWindowsPlatformTypes.h"
#include <commctrl.h>
#include <shellapi.h>
#include "Windows/HideWindowsPlatformTypes.h"
#endif

DEFINE_LOG_CATEGORY_STATIC(LogWindowDesktop, Log, All);

#if PLATFORM_WINDOWS
namespace
{
struct FDesktopSession
{
	RECT FullBounds = {};
	bool bHasBounds = false;
	bool bClickThrough = false;
	bool bDesktopMode = true;
	bool bCompact = false;
};
FDesktopSession DesktopSession;
HANDLE ProcessMutex = nullptr;
HANDLE RestoreEvent = nullptr;
}
#endif

struct FWindowDesktop::FImpl
{
	TWeakObjectPtr<AWindowDirector> Director;
	bool bDisabled = false;

#if PLATFORM_WINDOWS
	static constexpr UINT TrayMessage = WM_APP + 0x317;
	static constexpr UINT TrayId = 1;
	static constexpr UINT_PTR SubclassId = 0x4F4F57;
	enum EMenu : UINT { Show = 1, Hide, ClickThrough, DesktopMode, Compact, Exit };
	HWND Window = nullptr;
	LONG_PTR OriginalExStyle = 0;
	RECT FullBounds = DesktopSession.FullBounds;
	COLORREF OriginalColorKey = 0;
	BYTE OriginalAlpha = 255;
	DWORD OriginalAlphaFlags = 0;
	UINT ShowInstanceMessage = 0;
	UINT TaskbarCreatedMessage = 0;
	bool bTrayReady = false;
	bool bClickThrough = DesktopSession.bClickThrough;
	bool bDesktopMode = DesktopSession.bDesktopMode;
	bool bCompact = DesktopSession.bCompact;
	bool bSubclassAttached = false;
	bool bOriginalTopmost = false;
	bool bTestPending = FParse::Param(FCommandLine::Get(), TEXT("OOWTestDesktop"));
	double TestReadyAt = FPlatformTime::Seconds() + 15;

	NOTIFYICONDATAW TrayData() const
	{
		NOTIFYICONDATAW Data = {};
		Data.cbSize = sizeof(Data);
		Data.hWnd = Window;
		Data.uID = TrayId;
		Data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP;
		Data.uCallbackMessage = TrayMessage;
		Data.hIcon = reinterpret_cast<HICON>(SendMessageW(Window, WM_GETICON, ICON_SMALL, 0));
		if (!Data.hIcon) Data.hIcon = reinterpret_cast<HICON>(GetClassLongPtrW(Window, GCLP_HICONSM));
		if (!Data.hIcon) Data.hIcon = LoadIconW(nullptr, IDI_APPLICATION);
		FCString::Strncpy(Data.szTip, TEXT("Out of Window — 单击恢复窗景与鼠标交互"), UE_ARRAY_COUNT(Data.szTip));
		return Data;
	}

	void AddTray()
	{
		NOTIFYICONDATAW Data = TrayData();
		bTrayReady = Shell_NotifyIconW(NIM_ADD, &Data) != 0;
		if (bTrayReady)
		{
			Data.uVersion = NOTIFYICON_VERSION_4;
			Shell_NotifyIconW(NIM_SETVERSION, &Data);
		}
		else
		{
			// Never leave an invisible or click-through window without a recovery route.
			bDesktopMode = false;
			bClickThrough = false;
			UE_LOG(LogWindowDesktop, Warning, TEXT("Tray registration failed; keeping the game accessible in the taskbar."));
		}
	}

	void ApplyMode()
	{
		if (!IsWindow(Window)) return;
		LONG_PTR Style = GetWindowLongPtrW(Window, GWL_EXSTYLE);
		Style &= ~(WS_EX_TOOLWINDOW | WS_EX_APPWINDOW | WS_EX_TRANSPARENT | WS_EX_LAYERED);
		Style |= OriginalExStyle & (WS_EX_TOOLWINDOW | WS_EX_APPWINDOW | WS_EX_TRANSPARENT | WS_EX_LAYERED);
		if (bDesktopMode && bTrayReady) Style = (Style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW;
		if (bClickThrough && bTrayReady) Style |= WS_EX_LAYERED | WS_EX_TRANSPARENT;
		SetWindowLongPtrW(Window, GWL_EXSTYLE, Style);
		if (bClickThrough && bTrayReady)
		{
			// Both flags are needed for hit testing to pass through to other processes.
			SetLayeredWindowAttributes(Window, 0, 255, LWA_ALPHA);
		}
		else if ((OriginalExStyle & WS_EX_LAYERED) && OriginalAlphaFlags)
		{
			SetLayeredWindowAttributes(Window, OriginalColorKey, OriginalAlpha, OriginalAlphaFlags);
		}
		SetWindowPos(Window, bDesktopMode ? HWND_TOPMOST : HWND_NOTOPMOST, 0, 0, 0, 0,
			SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED);
	}

	void RestoreInteractive()
	{
		bClickThrough = false;
		ApplyMode();
		ShowWindow(Window, IsIconic(Window) ? SW_RESTORE : SW_SHOW);
		SetForegroundWindow(Window);
	}

	void HideSafely()
	{
		if (bTrayReady) ShowWindow(Window, SW_HIDE);
		else
		{
			bDesktopMode = false;
			bClickThrough = false;
			ApplyMode();
			ShowWindow(Window, SW_MINIMIZE);
		}
	}

	void ToggleCompact()
	{
		if (IsZoomed(Window) || IsIconic(Window)) ShowWindow(Window, SW_RESTORE);
		if (!bCompact) GetWindowRect(Window, &FullBounds);
		bCompact = !bCompact;
		if (Director.IsValid()) Director->SetCompactMode(bCompact);
		RECT Current = {};
		GetWindowRect(Window, &Current);
		const float Dpi = static_cast<float>(GetDpiForWindow(Window)) / 96.f;
		const int Width = bCompact ? FMath::RoundToInt(760.f * Dpi) : FullBounds.right - FullBounds.left;
		const int Height = bCompact ? FMath::RoundToInt(510.f * Dpi) : FullBounds.bottom - FullBounds.top;
		MONITORINFO Monitor = {};
		Monitor.cbSize = sizeof(Monitor);
		GetMonitorInfoW(MonitorFromWindow(Window, MONITOR_DEFAULTTONEAREST), &Monitor);
		const int FitWidth = FMath::Min(Width, static_cast<int>(Monitor.rcWork.right - Monitor.rcWork.left));
		const int FitHeight = FMath::Min(Height, static_cast<int>(Monitor.rcWork.bottom - Monitor.rcWork.top));
		const int X = FMath::Clamp(static_cast<int>(Current.left), static_cast<int>(Monitor.rcWork.left), static_cast<int>(Monitor.rcWork.right) - FitWidth);
		const int Y = FMath::Clamp(static_cast<int>(Current.top), static_cast<int>(Monitor.rcWork.top), static_cast<int>(Monitor.rcWork.bottom) - FitHeight);
		SetWindowPos(Window, nullptr, X, Y, FitWidth, FitHeight, SWP_NOZORDER | SWP_NOACTIVATE);
	}

	void Action(FName Name)
	{
		if (!IsWindow(Window)) return;
		if (Name == TEXT("Close")) HideSafely();
		else if (Name == TEXT("Minimize")) ShowWindow(Window, SW_MINIMIZE);
		else if (Name == TEXT("Maximize")) ShowWindow(Window, IsZoomed(Window) ? SW_RESTORE : SW_MAXIMIZE);
		else if (Name == TEXT("ClickThrough"))
		{
			if (bTrayReady) bClickThrough = !bClickThrough;
			ApplyMode();
		}
		else if (Name == TEXT("DesktopMode")) { bDesktopMode = !bDesktopMode; ApplyMode(); }
		else if (Name == TEXT("Compact")) ToggleCompact();
		else if (Name == TEXT("ToggleVisible"))
		{
			if (IsWindowVisible(Window) && !IsIconic(Window)) HideSafely(); else RestoreInteractive();
		}
	}

	void ShowTrayMenu()
	{
		HMENU Menu = CreatePopupMenu();
		if (!Menu) return;
		AppendMenuW(Menu, MF_STRING, Show, L"显示并恢复鼠标交互");
		AppendMenuW(Menu, MF_STRING, Hide, L"隐藏窗景");
		AppendMenuW(Menu, MF_STRING | (bClickThrough ? MF_CHECKED : 0), ClickThrough, L"鼠标穿透");
		AppendMenuW(Menu, MF_STRING | (bDesktopMode ? MF_CHECKED : 0), DesktopMode, L"桌面挂件模式（置顶）");
		AppendMenuW(Menu, MF_STRING | (bCompact ? MF_CHECKED : 0), Compact, L"精简尺寸");
		AppendMenuW(Menu, MF_SEPARATOR, 0, nullptr);
		AppendMenuW(Menu, MF_STRING, Exit, L"退出");
		POINT Cursor;
		GetCursorPos(&Cursor);
		SetForegroundWindow(Window);
		const UINT Choice = TrackPopupMenu(Menu, TPM_RETURNCMD | TPM_NONOTIFY | TPM_RIGHTBUTTON,
			Cursor.x, Cursor.y, 0, Window, nullptr);
		DestroyMenu(Menu);
		PostMessageW(Window, WM_NULL, 0, 0);
		switch (Choice)
		{
		case Show: RestoreInteractive(); break;
		case Hide: HideSafely(); break;
		case ClickThrough: Action(TEXT("ClickThrough")); break;
		case DesktopMode: Action(TEXT("DesktopMode")); break;
		case Compact: Action(TEXT("Compact")); break;
		case Exit: FPlatformMisc::RequestExit(false); break;
		default: break;
		}
	}

	void TestIfReady()
	{
		if (!bTestPending) return;
		if (bDisabled || (!IsWindow(Window) && FPlatformTime::Seconds() >= TestReadyAt))
		{
			bTestPending = false;
			UE_LOG(LogWindowDesktop, Error, TEXT("OOW_DESKTOP_TEST_FAIL native game window unavailable"));
			return;
		}
		if (!IsWindow(Window) || FPlatformTime::Seconds() < TestReadyAt) return;
		bTestPending = false;
		DWORD OwnerProcess = 0;
		GetWindowThreadProcessId(Window, &OwnerProcess);
		if (OwnerProcess != GetCurrentProcessId())
		{
			UE_LOG(LogWindowDesktop, Error, TEXT("OOW_DESKTOP_TEST_FAIL window ownership changed"));
			return;
		}
		TArray<TSharedPtr<FJsonValue>> Checks;
		bool bPassed = true;
		auto Record = [&](const TCHAR* Name, bool bOK)
		{
			const LONG_PTR Style = GetWindowLongPtrW(Window, GWL_EXSTYLE);
			RECT Bounds = {}; GetWindowRect(Window, &Bounds);
			TSharedRef<FJsonObject> Check = MakeShared<FJsonObject>();
			Check->SetStringField(TEXT("name"), Name);
			Check->SetBoolField(TEXT("passed"), bOK);
			Check->SetBoolField(TEXT("visible"), IsWindowVisible(Window) != 0);
			Check->SetBoolField(TEXT("minimized"), IsIconic(Window) != 0);
			Check->SetBoolField(TEXT("topmost"), (Style & WS_EX_TOPMOST) != 0);
			Check->SetBoolField(TEXT("toolWindow"), (Style & WS_EX_TOOLWINDOW) != 0);
			Check->SetBoolField(TEXT("appWindow"), (Style & WS_EX_APPWINDOW) != 0);
			Check->SetBoolField(TEXT("transparent"), (Style & WS_EX_TRANSPARENT) != 0);
			Check->SetBoolField(TEXT("layered"), (Style & WS_EX_LAYERED) != 0);
			Check->SetNumberField(TEXT("width"), Bounds.right - Bounds.left);
			Check->SetNumberField(TEXT("height"), Bounds.bottom - Bounds.top);
			Checks.Add(MakeShared<FJsonValueObject>(Check));
			bPassed &= bOK;
		};
		const bool bSavedCompact = bCompact, bSavedDesktop = bDesktopMode, bSavedMaximized = IsZoomed(Window) != 0;
		const RECT SavedFullBounds = FullBounds;
		RECT SavedBounds = {}; GetWindowRect(Window, &SavedBounds);
		RestoreInteractive();
		if (IsZoomed(Window)) ShowWindow(Window, SW_RESTORE);
		if (bCompact) Action(TEXT("Compact"));
		RECT NormalBounds = {}; GetWindowRect(Window, &NormalBounds);
		NOTIFYICONDATAW Data = TrayData();
		Record(TEXT("trayRegistered"), bTrayReady && Shell_NotifyIconW(NIM_MODIFY, &Data) != 0);
		Action(TEXT("Compact"));
		RECT CompactBounds = {}; GetWindowRect(Window, &CompactBounds);
		MONITORINFO Monitor = {}; Monitor.cbSize = sizeof(Monitor);
		const bool bMonitorRead = GetMonitorInfoW(MonitorFromWindow(Window, MONITOR_DEFAULTTONEAREST), &Monitor) != 0;
		const float Dpi = static_cast<float>(GetDpiForWindow(Window)) / 96.f;
		Record(TEXT("compactSize"), bMonitorRead && CompactBounds.right - CompactBounds.left == FMath::Min(FMath::RoundToInt(760 * Dpi), static_cast<int>(Monitor.rcWork.right - Monitor.rcWork.left)) && CompactBounds.bottom - CompactBounds.top == FMath::Min(FMath::RoundToInt(510 * Dpi), static_cast<int>(Monitor.rcWork.bottom - Monitor.rcWork.top)));
		Action(TEXT("Compact"));
		RECT RestoredBounds = {}; GetWindowRect(Window, &RestoredBounds);
		Record(TEXT("compactRestored"), RestoredBounds.right - RestoredBounds.left == NormalBounds.right - NormalBounds.left && RestoredBounds.bottom - RestoredBounds.top == NormalBounds.bottom - NormalBounds.top);
		if (!bDesktopMode) Action(TEXT("DesktopMode"));
		LONG_PTR Style = GetWindowLongPtrW(Window, GWL_EXSTYLE);
		Record(TEXT("desktopTopmostAndTaskbarStyles"), (Style & WS_EX_TOPMOST) && (Style & WS_EX_TOOLWINDOW) && !(Style & WS_EX_APPWINDOW));
		Action(TEXT("DesktopMode"));
		Style = GetWindowLongPtrW(Window, GWL_EXSTYLE);
		Record(TEXT("desktopModeRestored"), !(Style & WS_EX_TOPMOST) && (Style & (WS_EX_TOOLWINDOW | WS_EX_APPWINDOW)) == (OriginalExStyle & (WS_EX_TOOLWINDOW | WS_EX_APPWINDOW)));
		Action(TEXT("ClickThrough"));
		Style = GetWindowLongPtrW(Window, GWL_EXSTYLE);
		COLORREF ColorKey = 0; BYTE Alpha = 0; DWORD AlphaFlags = 0;
		const bool bLayeredRead = GetLayeredWindowAttributes(Window, &ColorKey, &Alpha, &AlphaFlags) != 0;
		Record(TEXT("clickThroughEnabled"), (Style & WS_EX_TRANSPARENT) && (Style & WS_EX_LAYERED) && bLayeredRead && Alpha == 255 && (AlphaFlags & LWA_ALPHA));
		RestoreInteractive();
		Record(TEXT("clickThroughRestored"), !(GetWindowLongPtrW(Window, GWL_EXSTYLE) & WS_EX_TRANSPARENT));
		Action(TEXT("Close"));
		Record(TEXT("hidden"), !IsWindowVisible(Window));
		RestoreInteractive();
		Record(TEXT("hiddenRestored"), IsWindowVisible(Window) && !IsIconic(Window));
		Action(TEXT("Minimize"));
		Record(TEXT("minimized"), IsIconic(Window) != 0);
		RestoreInteractive();
		Record(TEXT("minimizeRestored"), IsWindowVisible(Window) && !IsIconic(Window));
		if (bCompact != bSavedCompact) Action(TEXT("Compact"));
		if (bDesktopMode != bSavedDesktop) Action(TEXT("DesktopMode"));
		FullBounds = SavedFullBounds;
		SetWindowPos(Window, nullptr, SavedBounds.left, SavedBounds.top, SavedBounds.right - SavedBounds.left, SavedBounds.bottom - SavedBounds.top, SWP_NOZORDER | SWP_NOACTIVATE);
		if (bSavedMaximized) ShowWindow(Window, SW_MAXIMIZE);
		RestoreInteractive();
		Record(TEXT("finalInteractive"), IsWindowVisible(Window) && !IsIconic(Window) && !(GetWindowLongPtrW(Window, GWL_EXSTYLE) & WS_EX_TRANSPARENT));
		TSharedRef<FJsonObject> Report = MakeShared<FJsonObject>();
		Report->SetBoolField(TEXT("passed"), bPassed);
		Report->SetNumberField(TEXT("processId"), OwnerProcess);
		Report->SetBoolField(TEXT("humanTrayClickTested"), false);
		Report->SetArrayField(TEXT("checks"), Checks);
		FString Text, Capture;
		FJsonSerializer::Serialize(Report, TJsonWriterFactory<>::Create(&Text));
		const FString Path = FParse::Value(FCommandLine::Get(), TEXT("OOWCapture="), Capture) ? FPaths::ChangeExtension(Capture, TEXT("desktop.json")) : FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("oow-desktop-test.json"));
		IFileManager::Get().MakeDirectory(*FPaths::GetPath(Path), true);
		const bool bSaved = FFileHelper::SaveStringToFile(Text, *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
		if (bPassed && bSaved) { UE_LOG(LogWindowDesktop, Display, TEXT("OOW_DESKTOP_TEST_PASS %s"), *Path); }
		else { UE_LOG(LogWindowDesktop, Error, TEXT("OOW_DESKTOP_TEST_FAIL %s saved=%d"), *Path, bSaved); }
	}

	static LRESULT CALLBACK WindowProc(HWND Hwnd, UINT Message, WPARAM WParam, LPARAM LParam, UINT_PTR Id, DWORD_PTR User)
	{
		FImpl* Self = reinterpret_cast<FImpl*>(User);
		if (Message == WM_CLOSE || (Message == WM_SYSCOMMAND && (WParam & 0xFFF0) == SC_CLOSE))
		{
			Self->HideSafely();
			return 0;
		}
		if (Message == Self->ShowInstanceMessage) { Self->RestoreInteractive(); return 0; }
		if (Message == Self->TaskbarCreatedMessage) { Self->AddTray(); Self->ApplyMode(); return 0; }
		if (Message == TrayMessage)
		{
			const UINT Event = LOWORD(LParam);
			if (Event == NIN_SELECT || Event == NIN_KEYSELECT || Event == WM_LBUTTONUP) Self->RestoreInteractive();
			else if (Event == WM_CONTEXTMENU || Event == WM_RBUTTONUP) Self->ShowTrayMenu();
			return 0;
		}
		if (Message == WM_NCHITTEST && Self->bClickThrough) return HTTRANSPARENT;
		if (Message == WM_NCDESTROY)
		{
			NOTIFYICONDATAW Data = Self->TrayData();
			Shell_NotifyIconW(NIM_DELETE, &Data);
			RemoveWindowSubclass(Hwnd, WindowProc, Id);
			Self->bTrayReady = false;
			Self->bSubclassAttached = false;
			Self->Window = nullptr;
			Self->bDisabled = true;
		}
		return DefSubclassProc(Hwnd, Message, WParam, LParam);
	}

	void TryAttach()
	{
		if (bDisabled || Window || !Director.IsValid()) return;
		UWorld* World = Director->GetWorld();
		// In particular, never resolve the editor's top-level HWND through PIE.
		if (!World || World->WorldType != EWorldType::Game) { bDisabled = true; return; }
		if (!FSlateApplication::IsInitialized()) return;
		UGameViewportClient* Viewport = World->GetGameViewport();
		const TSharedPtr<SWindow> SlateWindow = Viewport ? Viewport->GetWindow() : nullptr;
		if (!SlateWindow.IsValid() || !SlateWindow->GetNativeWindow().IsValid()) return;
		Window = static_cast<HWND>(SlateWindow->GetNativeWindow()->GetOSWindowHandle());
		if (!IsWindow(Window)) { Window = nullptr; return; }
		DWORD OwnerProcess = 0;
		GetWindowThreadProcessId(Window, &OwnerProcess);
		if (OwnerProcess != GetCurrentProcessId()) { Window = nullptr; bDisabled = true; return; }
		ShowInstanceMessage = RegisterWindowMessageW(L"OutOfWindow.Native.ShowInstance.v1");
		TaskbarCreatedMessage = RegisterWindowMessageW(L"TaskbarCreated");
		OriginalExStyle = GetWindowLongPtrW(Window, GWL_EXSTYLE);
		bOriginalTopmost = (OriginalExStyle & WS_EX_TOPMOST) != 0;
		if (!DesktopSession.bHasBounds) GetWindowRect(Window, &FullBounds);
		if (OriginalExStyle & WS_EX_LAYERED) GetLayeredWindowAttributes(Window, &OriginalColorKey, &OriginalAlpha, &OriginalAlphaFlags);
		bSubclassAttached = SetWindowSubclass(Window, WindowProc, SubclassId, reinterpret_cast<DWORD_PTR>(this)) != 0;
		if (!bSubclassAttached)
		{
			UE_LOG(LogWindowDesktop, Error, TEXT("Cannot attach to the standalone viewport window; desktop controls disabled."));
			Window = nullptr;
			bDisabled = true;
			return;
		}
		AddTray();
		ApplyMode();
		Director->SetCompactMode(bCompact);
		TestReadyAt = FPlatformTime::Seconds() + 2;
	}

	void Shutdown()
	{
		if (IsWindow(Window))
		{
			DesktopSession.FullBounds = FullBounds;
			DesktopSession.bHasBounds = true;
			DesktopSession.bClickThrough = bClickThrough;
			DesktopSession.bDesktopMode = bDesktopMode;
			DesktopSession.bCompact = bCompact;
			NOTIFYICONDATAW Data = TrayData();
			Shell_NotifyIconW(NIM_DELETE, &Data);
			if (bSubclassAttached) RemoveWindowSubclass(Window, WindowProc, SubclassId);
			SetWindowLongPtrW(Window, GWL_EXSTYLE, OriginalExStyle);
			if ((OriginalExStyle & WS_EX_LAYERED) && OriginalAlphaFlags)
				SetLayeredWindowAttributes(Window, OriginalColorKey, OriginalAlpha, OriginalAlphaFlags);
			SetWindowPos(Window, bOriginalTopmost ? HWND_TOPMOST : HWND_NOTOPMOST, 0, 0, 0, 0,
				SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED);
		}
		Window = nullptr;
		bTrayReady = bSubclassAttached = false;
	}
#else
	void Action(FName) {}
	void TryAttach() { bDisabled = true; }
	void TestIfReady() {}
	void Shutdown() {}
#endif
};

void FWindowDesktop::InitializeProcess()
{
#if PLATFORM_WINDOWS
	if (GIsEditor || IsRunningCommandlet() || IsRunningDedicatedServer()) return;
	FString Capture;
	const bool bDesktopTest = FParse::Param(FCommandLine::Get(), TEXT("OOWTestDesktop"));
	if (!bDesktopTest && FParse::Value(FCommandLine::Get(), TEXT("OOWCapture="), Capture)) return;
	RestoreEvent = CreateEventW(nullptr, false, false, L"Local\\OutOfWindow.Native.Restore.v1");
	ProcessMutex = CreateMutexW(nullptr, false, L"Local\\OutOfWindow.Native.Desktop.v1");
	const DWORD MutexStatus = GetLastError();
	if (ProcessMutex && MutexStatus == ERROR_ALREADY_EXISTS)
	{
		const bool bNotified = !bDesktopTest && RestoreEvent && SetEvent(RestoreEvent);
		UE_LOG(LogWindowDesktop, Display, TEXT("OOW_DUPLICATE_INSTANCE early exit; restoreSignaled=%d"), bNotified);
		if (bDesktopTest) { UE_LOG(LogWindowDesktop, Error, TEXT("OOW_DESKTOP_TEST_FAIL another app instance is running")); }
		ShutdownProcess();
		// This duplicate has no world or user state; bypass expensive engine teardown.
		FPlatformMisc::RequestExitWithStatus(true, bDesktopTest ? 1 : 0, TEXT("OutOfWindow duplicate instance"));
	}
	else if (!ProcessMutex)
	{
		UE_LOG(LogWindowDesktop, Warning, TEXT("Single-instance mutex unavailable: %lu"), MutexStatus);
	}
#endif
}

void FWindowDesktop::ShutdownProcess()
{
#if PLATFORM_WINDOWS
	if (ProcessMutex) CloseHandle(ProcessMutex);
	if (RestoreEvent) CloseHandle(RestoreEvent);
	ProcessMutex = RestoreEvent = nullptr;
#endif
}

FWindowDesktop::FWindowDesktop() : Impl(MakeUnique<FImpl>()) {}
FWindowDesktop::~FWindowDesktop() { Shutdown(); }

void FWindowDesktop::Initialize(AWindowDirector* Director)
{
	if (!Director) return;
	Impl->Director = Director;
	Director->DesktopAction = [this](FName Name) { Impl->Action(Name); };
	Impl->TryAttach();
}

void FWindowDesktop::Tick()
{
	Impl->TryAttach();
#if PLATFORM_WINDOWS
	if (IsWindow(Impl->Window) && RestoreEvent && WaitForSingleObject(RestoreEvent, 0) == WAIT_OBJECT_0) Impl->RestoreInteractive();
#endif
	Impl->TestIfReady();
}

void FWindowDesktop::Shutdown()
{
	if (!Impl) return;
	if (Impl->Director.IsValid()) Impl->Director->DesktopAction = nullptr;
	Impl->Director.Reset();
	Impl->Shutdown();
}
