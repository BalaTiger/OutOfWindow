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
#include "Layout/WidgetPath.h"

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
	bool bDesktopMode = true;
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
	enum EMenu : UINT { Show = 1, Hide, DesktopMode, Exit };
	HWND Window = nullptr;
	HWND DesktopHost = nullptr, IconView = nullptr;
	LONG_PTR OriginalStyle = 0;
	RECT WindowedBounds = {};
	HHOOK MouseHook = nullptr, EscapeHook = nullptr;
	inline static FImpl* InputOwner = nullptr;
	bool bForwardLeft = false;
	static constexpr UINT RestoreUIMessage = WM_APP + 0x318;
	LONG_PTR OriginalExStyle = 0;
	UINT ShowInstanceMessage = 0;
	UINT TaskbarCreatedMessage = 0;
	bool bTrayReady = false;
	bool bDesktopMode = false;
	bool bSubclassAttached = false;
	bool bOriginalTopmost = false;
	const uint64 AttachAfterFrame = GFrameCounter + 2;
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
		FCString::Strncpy(Data.szTip, TEXT("Out of Window — 单击显示窗景"), UE_ARRAY_COUNT(Data.szTip));
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
			// Keep a taskbar recovery route when the tray is unavailable.
			bDesktopMode = false;
			UE_LOG(LogWindowDesktop, Warning, TEXT("Tray registration failed; keeping the game accessible in the taskbar."));
		}
	}

	TSharedPtr<SWindow> SlateWindow() const
	{
		UGameViewportClient* Viewport = Director.IsValid() ? Director->GetWorld()->GetGameViewport() : nullptr;
		return Viewport ? Viewport->GetWindow() : nullptr;
	}

	bool IsShellWindow(HWND Handle) const
	{
		if (!Handle) return false;
		WCHAR Class[64] = {};
		GetClassNameW(Handle, Class, UE_ARRAY_COUNT(Class));
		return Handle == DesktopHost || Handle == IconView || Handle == FindWindowExW(IconView, nullptr, L"SysListView32", nullptr)
			|| !wcscmp(Class, L"Progman") || !wcscmp(Class, L"WorkerW");
	}

	bool IsControlAt(POINT Position) const
	{
		const auto Slate = SlateWindow();
		if (!Slate || !IsWindowVisible(Window)) return false;
		const FWidgetPath Path = FSlateApplication::Get().LocateWindowUnderMouse(FVector2D(Position.x, Position.y), { Slate.ToSharedRef() }, false, 0);
		for (int32 Index = 0; Index < Path.Widgets.Num(); ++Index)
		{
			const FArrangedWidget& Item = Path.Widgets[Index];
			const FName Type = Item.Widget->GetType();
			if (Type == TEXT("SButton") || Type == TEXT("SWindowVisibilityButton") || Type == TEXT("SSlider") || Type == TEXT("SComboButton")) return Item.Widget->IsEnabled();
		}
		return false;
	}

	static LRESULT CALLBACK MouseInput(int Code, WPARAM Message, LPARAM Data)
	{
		FImpl* Self = InputOwner;
		if (Code == HC_ACTION && Self && Self->bDesktopMode && IsWindowVisible(Self->Window))
		{
			const POINT Screen = reinterpret_cast<MSLLHOOKSTRUCT*>(Data)->pt;
			const bool bOnDesktop = Self->IsShellWindow(WindowFromPoint(Screen));
			const bool bControl = bOnDesktop && Self->IsControlAt(Screen);
			bool bConsume = false;
			if (Message == WM_LBUTTONDOWN && bControl) Self->bForwardLeft = bConsume = true;
			if (Message == WM_LBUTTONUP && Self->bForwardLeft) { Self->bForwardLeft = false; bConsume = true; }
			if ((Message == WM_MOUSEMOVE && (bOnDesktop || Self->bForwardLeft)) || bConsume)
			{
				POINT Client = Screen; ScreenToClient(Self->Window, &Client);
				PostMessageW(Self->Window, static_cast<UINT>(Message), Self->bForwardLeft ? MK_LBUTTON : 0, MAKELPARAM(Client.x, Client.y));
			}
			if (bConsume) return 1;
		}
		return CallNextHookEx(nullptr, Code, Message, Data);
	}

	static LRESULT CALLBACK EscapeInput(int Code, WPARAM Message, LPARAM Data)
	{
		FImpl* Self = InputOwner;
		if (Code == HC_ACTION && Message == WM_KEYDOWN && Self && Self->bDesktopMode
			&& reinterpret_cast<KBDLLHOOKSTRUCT*>(Data)->vkCode == VK_ESCAPE && Self->IsShellWindow(GetForegroundWindow()))
			PostMessageW(Self->Window, RestoreUIMessage, 0, 0);
		return CallNextHookEx(nullptr, Code, Message, Data);
	}

	void StopInput()
	{
		if (MouseHook) UnhookWindowsHookEx(MouseHook);
		if (EscapeHook) UnhookWindowsHookEx(EscapeHook);
		MouseHook = EscapeHook = nullptr;
		bForwardLeft = false;
		if (InputOwner == this) InputOwner = nullptr;
	}

	void RestoreWindow(bool bActivate)
	{
		StopInput();
		if (!IsWindow(Window)) return;
		if (bDesktopMode)
		{
			SetParent(Window, nullptr);
			SetWindowLongPtrW(Window, GWL_STYLE, OriginalStyle);
			SetWindowLongPtrW(Window, GWL_EXSTYLE, (OriginalExStyle | WS_EX_APPWINDOW) & ~(WS_EX_TOPMOST | WS_EX_TOOLWINDOW));
			SetWindowPos(Window, HWND_NOTOPMOST, WindowedBounds.left, WindowedBounds.top,
				WindowedBounds.right - WindowedBounds.left, WindowedBounds.bottom - WindowedBounds.top, SWP_FRAMECHANGED | SWP_NOACTIVATE);
			bDesktopMode = false;
		}
		DesktopHost = IconView = nullptr;
		if (bActivate) { ShowWindow(Window, SW_RESTORE); SetForegroundWindow(Window); }
	}

	bool EnterDesktop()
	{
		if (bDesktopMode) return true;
		HWND Progman = FindWindowW(L"Progman", nullptr);
		if (!Progman || !bTrayReady) return false;
		DWORD_PTR Result = 0;
		SendMessageTimeoutW(Progman, 0x052C, 0xD, 1, SMTO_ABORTIFHUNG, 1000, &Result);
		IconView = FindWindowExW(Progman, nullptr, L"SHELLDLL_DefView", nullptr);
		const bool bRaisedDesktop = (GetWindowLongPtrW(Progman, GWL_EXSTYLE) & WS_EX_NOREDIRECTIONBITMAP) != 0;
		if (bRaisedDesktop && IconView) DesktopHost = Progman;
		else
		{
			EnumWindows([](HWND Candidate, LPARAM Context) -> BOOL
			{
				FImpl* Self = reinterpret_cast<FImpl*>(Context);
				if (HWND Icons = FindWindowExW(Candidate, nullptr, L"SHELLDLL_DefView", nullptr))
				{
					Self->IconView = Icons;
					Self->DesktopHost = FindWindowExW(nullptr, Candidate, L"WorkerW", nullptr);
					if (Self->DesktopHost) return 0;
				}
				return 1;
			}, reinterpret_cast<LPARAM>(this));
		}
		if (!DesktopHost || !IconView) { DesktopHost = IconView = nullptr; return false; }
		MONITORINFO Monitor = {}; Monitor.cbSize = sizeof(Monitor);
		if (!GetMonitorInfoW(MonitorFromWindow(Window, MONITOR_DEFAULTTONEAREST), &Monitor)) return false;
		if (IsZoomed(Window) || IsIconic(Window)) ShowWindow(Window, SW_RESTORE);
		GetWindowRect(Window, &WindowedBounds);
		if (const auto Slate = SlateWindow()) Slate->ReshapeWindow(FVector2D(Monitor.rcMonitor.left, Monitor.rcMonitor.top), FVector2D(Monitor.rcMonitor.right - Monitor.rcMonitor.left, Monitor.rcMonitor.bottom - Monitor.rcMonitor.top));
		SetWindowPos(Window, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
		SetWindowLongPtrW(Window, GWL_STYLE, (OriginalStyle | WS_CHILD) & ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME));
		SetWindowLongPtrW(Window, GWL_EXSTYLE, (OriginalExStyle | WS_EX_TOOLWINDOW | (bRaisedDesktop ? WS_EX_LAYERED : 0)) & ~(WS_EX_APPWINDOW | WS_EX_TOPMOST));
		if (bRaisedDesktop) SetLayeredWindowAttributes(Window, 0, 255, LWA_ALPHA);
		SetLastError(0);
		SetParent(Window, DesktopHost);
		const DWORD Error = GetLastError();
		bDesktopMode = true; // Also permits rollback if SetParent failed.
		if (GetParent(Window) != DesktopHost)
		{
			UE_LOG(LogWindowDesktop, Error, TEXT("Desktop attachment failed: %lu"), Error);
			RestoreWindow(true); return false;
		}
		POINT Origin = { Monitor.rcMonitor.left, Monitor.rcMonitor.top }; ScreenToClient(DesktopHost, &Origin);
		SetWindowPos(Window, bRaisedDesktop ? IconView : HWND_BOTTOM, Origin.x, Origin.y,
			Monitor.rcMonitor.right - Monitor.rcMonitor.left, Monitor.rcMonitor.bottom - Monitor.rcMonitor.top, SWP_FRAMECHANGED | SWP_NOACTIVATE | SWP_SHOWWINDOW);
		InputOwner = this;
		MouseHook = SetWindowsHookExW(WH_MOUSE_LL, MouseInput, GetModuleHandleW(nullptr), 0);
		EscapeHook = SetWindowsHookExW(WH_KEYBOARD_LL, EscapeInput, GetModuleHandleW(nullptr), 0);
		if (!MouseHook || !EscapeHook) { RestoreWindow(true); return false; }
		UE_LOG(LogWindowDesktop, Display, TEXT("OOW_DESKTOP_ATTACHED raised=%d width=%ld height=%ld"), bRaisedDesktop, Monitor.rcMonitor.right - Monitor.rcMonitor.left, Monitor.rcMonitor.bottom - Monitor.rcMonitor.top);
		return true;
	}

	void RestoreInteractive()
	{
		if (bDesktopMode) { ShowWindow(Window, SW_SHOWNA); return; }
		ShowWindow(Window, IsIconic(Window) ? SW_RESTORE : SW_SHOW);
		SetForegroundWindow(Window);
	}

	void HideSafely()
	{
		if (bTrayReady) ShowWindow(Window, SW_HIDE);
		else
		{
			RestoreWindow(false);
			ShowWindow(Window, SW_MINIMIZE);
		}
	}

	void Action(FName Name)
	{
		if (!IsWindow(Window)) return;
		if (Name == TEXT("Close")) HideSafely();
		else if (Name == TEXT("Minimize")) { if (bDesktopMode) HideSafely(); else ShowWindow(Window, SW_MINIMIZE); }
		else if (Name == TEXT("Maximize") || Name == TEXT("DesktopMode"))
		{
			if (bDesktopMode) RestoreWindow(true);
			else if (!EnterDesktop()) UE_LOG(LogWindowDesktop, Warning, TEXT("Desktop unavailable; retaining the interactive window."));
		}
		else if (Name == TEXT("ToggleVisible"))
		{
			if (IsWindowVisible(Window) && !IsIconic(Window)) HideSafely(); else RestoreInteractive();
		}
	}

	void ShowTrayMenu()
	{
		HMENU Menu = CreatePopupMenu();
		if (!Menu) return;
		AppendMenuW(Menu, MF_STRING, Show, L"显示窗景");
		AppendMenuW(Menu, MF_STRING, Hide, L"隐藏窗景");
		AppendMenuW(Menu, MF_STRING, DesktopMode, bDesktopMode ? L"还原为窗口" : L"最大化为动态桌面");
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
		case DesktopMode: Action(TEXT("DesktopMode")); break;
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
			Check->SetBoolField(TEXT("desktopMode"), bDesktopMode);
			Check->SetBoolField(TEXT("visible"), IsWindowVisible(Window) != 0);
			Check->SetBoolField(TEXT("minimized"), IsIconic(Window) != 0);
			Check->SetBoolField(TEXT("topmost"), (Style & WS_EX_TOPMOST) != 0);
			Check->SetBoolField(TEXT("toolWindow"), (Style & WS_EX_TOOLWINDOW) != 0);
			Check->SetBoolField(TEXT("appWindow"), (Style & WS_EX_APPWINDOW) != 0);
			Check->SetNumberField(TEXT("width"), Bounds.right - Bounds.left);
			Check->SetNumberField(TEXT("height"), Bounds.bottom - Bounds.top);
			Check->SetNumberField(TEXT("left"), Bounds.left);
			Check->SetNumberField(TEXT("top"), Bounds.top);
			Checks.Add(MakeShared<FJsonValueObject>(Check));
			bPassed &= bOK;
		};
		const bool bSavedDesktop = bDesktopMode;
		auto Attached = [&]
		{
			const HWND IconLayer = GetParent(IconView) == DesktopHost ? IconView : GetAncestor(IconView, GA_ROOT);
			const HWND SceneLayer = GetParent(IconView) == DesktopHost ? Window : DesktopHost;
			bool bBehindIcons = false;
			for (HWND Layer = GetWindow(IconLayer, GW_HWNDNEXT); Layer; Layer = GetWindow(Layer, GW_HWNDNEXT))
				if (Layer == SceneLayer) { bBehindIcons = true; break; }
			return bDesktopMode && IsWindow(DesktopHost) && GetParent(Window) == DesktopHost
				&& bBehindIcons && (GetWindowLongPtrW(Window, GWL_STYLE) & WS_CHILD) && !(GetWindowLongPtrW(Window, GWL_EXSTYLE) & WS_EX_TOPMOST);
		};
		auto CoversMonitor = [&]
		{
			MONITORINFO Monitor = {}; Monitor.cbSize = sizeof(Monitor);
			RECT Bounds = {}, Client = {}; POINT Origin = {};
			GetWindowRect(Window, &Bounds); GetClientRect(Window, &Client); ClientToScreen(Window, &Origin); OffsetRect(&Client, Origin.x, Origin.y);
			return GetMonitorInfoW(MonitorFromWindow(Window, MONITOR_DEFAULTTONEAREST), &Monitor)
				&& EqualRect(&Bounds, &Monitor.rcMonitor) && EqualRect(&Client, &Monitor.rcMonitor);
		};
		NOTIFYICONDATAW Data = TrayData();
		Record(TEXT("trayRegistered"), bTrayReady && Shell_NotifyIconW(NIM_MODIFY, &Data) != 0);
		Record(TEXT("defaultDesktopParentAndZOrder"), Attached());
		Record(TEXT("desktopCoversMonitorAndClient"), CoversMonitor());
		Record(TEXT("desktopInputHooksReady"), MouseHook && EscapeHook);
		const RECT SavedBounds = WindowedBounds;
		Action(TEXT("Maximize"));
		RECT Restored = {}; GetWindowRect(Window, &Restored);
		Record(TEXT("restoreDetachesAndRestoresPlacement"), !bDesktopMode && !GetParent(Window) && EqualRect(&Restored, &SavedBounds) && !(GetWindowLongPtrW(Window, GWL_STYLE) & WS_CHILD));
		Record(TEXT("windowedInputHooksRemoved"), !MouseHook && !EscapeHook);
		Action(TEXT("Minimize"));
		Record(TEXT("windowedMinimized"), IsIconic(Window) != 0);
		RestoreInteractive();
		Record(TEXT("windowedMinimizeRestored"), IsWindowVisible(Window) && !IsIconic(Window));
		Action(TEXT("Maximize"));
		Record(TEXT("maximizeReturnsToDesktop"), Attached() && CoversMonitor());
		Action(TEXT("Close"));
		Record(TEXT("desktopHidden"), !IsWindowVisible(Window));
		RestoreInteractive();
		Record(TEXT("desktopShownWithoutWindowing"), IsWindowVisible(Window) && Attached() && CoversMonitor());
		Action(TEXT("Maximize"));
		GetWindowRect(Window, &Restored);
		Record(TEXT("repeatedRestorePreservesPlacement"), !bDesktopMode && EqualRect(&Restored, &SavedBounds));
		if (bSavedDesktop) Action(TEXT("Maximize"));
		Record(TEXT("finalModePreserved"), bDesktopMode == bSavedDesktop);
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
		if (Message == RestoreUIMessage)
		{
			if (Self->Director.IsValid() && Self->Director->RestoreInterface) Self->Director->RestoreInterface();
			return 0;
		}
		if (Message == WM_CLOSE || (Message == WM_SYSCOMMAND && (WParam & 0xFFF0) == SC_CLOSE))
		{
			Self->HideSafely();
			return 0;
		}
		if (Message == Self->ShowInstanceMessage) { Self->RestoreInteractive(); return 0; }
		if (Message == Self->TaskbarCreatedMessage) { Self->AddTray(); return 0; }
		if (Message == WM_SYSCOMMAND && ((WParam & 0xFFF0) == SC_MAXIMIZE || (WParam & 0xFFF0) == SC_RESTORE) && !IsIconic(Hwnd))
		{
			Self->Action(TEXT("Maximize")); return 0;
		}
		if (Message == TrayMessage)
		{
			const UINT Event = LOWORD(LParam);
			if (Event == NIN_SELECT || Event == NIN_KEYSELECT || Event == WM_LBUTTONUP) Self->RestoreInteractive();
			else if (Event == WM_CONTEXTMENU || Event == WM_RBUTTONUP) Self->ShowTrayMenu();
			return 0;
		}
		if (Message == WM_NCDESTROY)
		{
			Self->StopInput();
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
		// Startup applies the viewport's initial placement after BeginPlay.
		if (GFrameCounter < AttachAfterFrame) return;
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
		OriginalStyle = GetWindowLongPtrW(Window, GWL_STYLE);
		bOriginalTopmost = (OriginalExStyle & WS_EX_TOPMOST) != 0;
		bSubclassAttached = SetWindowSubclass(Window, WindowProc, SubclassId, reinterpret_cast<DWORD_PTR>(this)) != 0;
		if (!bSubclassAttached)
		{
			UE_LOG(LogWindowDesktop, Error, TEXT("Cannot attach to the standalone viewport window; desktop controls disabled."));
			Window = nullptr;
			bDisabled = true;
			return;
		}
		AddTray();
		if (DesktopSession.bDesktopMode && !EnterDesktop()) UE_LOG(LogWindowDesktop, Warning, TEXT("Desktop unavailable at startup; using a window."));
		TestReadyAt = FPlatformTime::Seconds() + 2;
	}

	void Shutdown()
	{
		StopInput();
		if (IsWindow(Window))
		{
			DesktopSession.bDesktopMode = bDesktopMode;
			RestoreWindow(false);
			NOTIFYICONDATAW Data = TrayData();
			Shell_NotifyIconW(NIM_DELETE, &Data);
			if (bSubclassAttached) RemoveWindowSubclass(Window, WindowProc, SubclassId);
			SetWindowLongPtrW(Window, GWL_EXSTYLE, OriginalExStyle);
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

bool FWindowDesktop::IsDesktopMode() const
{
#if PLATFORM_WINDOWS
	return Impl->bDesktopMode;
#else
	return false;
#endif
}

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
