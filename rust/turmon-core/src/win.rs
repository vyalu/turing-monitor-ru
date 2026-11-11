//! Windows: значок в трее, выключение/сон/мониторы, одна копия программы.

use std::sync::{Arc, OnceLock};

use log::info;
use windows_sys::Win32::Foundation::{GetLastError, HWND, LPARAM, LRESULT, POINT, WPARAM, ERROR_ALREADY_EXISTS};
use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
use windows_sys::Win32::System::Power::{POWERBROADCAST_SETTING, RegisterPowerSettingNotification};
use windows_sys::Win32::System::Threading::{CreateMutexW, SetProcessShutdownParameters};
use windows_sys::Win32::UI::Shell::{
    NIF_ICON, NIF_MESSAGE, NIF_TIP, NIM_ADD, NIM_DELETE, NOTIFYICONDATAW, Shell_NotifyIconW,
};
use windows_sys::Win32::UI::WindowsAndMessaging::*;
use windows_sys::core::GUID;

use crate::engine::Engine;

const WM_TRAY: u32 = WM_APP + 1;
const ID_OPEN: usize = 1;
const ID_PAUSE: usize = 2;
const ID_RECONNECT: usize = 3;
const ID_QUIT: usize = 9;
const PBT_APMSUSPEND: usize = 0x4;
const PBT_APMRESUMESUSPEND: usize = 0x7;
const PBT_APMRESUMEAUTOMATIC: usize = 0x12;
const PBT_POWERSETTINGCHANGE: usize = 0x8013;
const GUID_CONSOLE_DISPLAY_STATE: GUID = GUID::from_u128(0x6FE69556_704A_47A0_8F24_C28D936FDA47);

static ENGINE: OnceLock<Arc<Engine>> = OnceLock::new();
static HWND_MAIN: std::sync::atomic::AtomicPtr<core::ffi::c_void> = std::sync::atomic::AtomicPtr::new(std::ptr::null_mut());

/// Выход из любого потока (команда «quit» от окна программы).
pub fn request_quit() {
    let h = HWND_MAIN.load(std::sync::atomic::Ordering::SeqCst);
    if !h.is_null() {
        unsafe {
            PostMessageW(h, WM_CLOSE, 0, 0);
        }
    }
}
static ON_OPEN: OnceLock<Box<dyn Fn() + Send + Sync>> = OnceLock::new();

fn w(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

/// Вторая копия? (именованный мьютекс; держим его до выхода).
pub fn already_running() -> bool {
    unsafe {
        let name = w("Local\\TuringMonitorRU-core");
        let h = CreateMutexW(std::ptr::null(), 1, name.as_ptr());
        !h.is_null() && GetLastError() == ERROR_ALREADY_EXISTS
    }
}

unsafe fn tray_menu(hwnd: HWND) {
    unsafe {
        let m = CreatePopupMenu();
        let paused = ENGINE.get().map(|e| e.paused()).unwrap_or(false);
        AppendMenuW(m, MF_STRING, ID_OPEN, w("Открыть Turing Monitor RU").as_ptr());
        AppendMenuW(m, MF_STRING, ID_PAUSE, w(if paused { "Включить мини-экран" } else { "Выключить мини-экран" }).as_ptr());
        AppendMenuW(m, MF_STRING, ID_RECONNECT, w("Переподключить экран").as_ptr());
        AppendMenuW(m, MF_SEPARATOR, 0, std::ptr::null());
        AppendMenuW(m, MF_STRING, ID_QUIT, w("Выход").as_ptr());
        let mut p = POINT { x: 0, y: 0 };
        GetCursorPos(&mut p);
        SetForegroundWindow(hwnd);
        TrackPopupMenu(m, TPM_RIGHTBUTTON, p.x, p.y, 0, hwnd, std::ptr::null());
        DestroyMenu(m);
    }
}

unsafe extern "system" fn wndproc(hwnd: HWND, msg: u32, wp: WPARAM, lp: LPARAM) -> LRESULT {
    unsafe {
        let e = ENGINE.get();
        match msg {
            WM_QUERYENDSESSION => {
                if let Some(e) = e {
                    e.shutdown_now();
                }
                return 1;
            }
            WM_ENDSESSION => {
                if wp != 0 {
                    if let Some(e) = e {
                        e.shutdown_now();
                    }
                }
                return 0;
            }
            WM_POWERBROADCAST => {
                if let Some(e) = e {
                    match wp {
                        PBT_APMSUSPEND => e.suspend(),
                        PBT_APMRESUMESUSPEND | PBT_APMRESUMEAUTOMATIC => e.resume(),
                        PBT_POWERSETTINGCHANGE if lp != 0 => {
                            let s = &*(lp as *const POWERBROADCAST_SETTING);
                            if s.PowerSetting.data1 == GUID_CONSOLE_DISPLAY_STATE.data1 {
                                e.set_monitor_off(s.Data[0] == 0);
                            }
                        }
                        _ => {}
                    }
                }
                return 1;
            }
            WM_CLOSE => {
                PostQuitMessage(0);
                return 0;
            }
            WM_TRAY => {
                let ev = (lp & 0xFFFF) as u32;
                if ev == WM_RBUTTONUP {
                    tray_menu(hwnd);
                } else if ev == WM_LBUTTONDBLCLK {
                    if let Some(f) = ON_OPEN.get() {
                        f();
                    }
                }
                return 0;
            }
            WM_COMMAND => {
                match wp & 0xFFFF {
                    ID_OPEN => {
                        if let Some(f) = ON_OPEN.get() {
                            f();
                        }
                    }
                    ID_PAUSE => {
                        if let Some(e) = e {
                            e.set_paused(!e.paused());
                        }
                    }
                    ID_RECONNECT => {
                        if let Some(e) = e {
                            e.reconnect(None);
                        }
                    }
                    ID_QUIT => PostQuitMessage(0),
                    _ => {}
                }
                return 0;
            }
            _ => {}
        }
        DefWindowProcW(hwnd, msg, wp, lp)
    }
}

/// Скрытое окно с значком в трее; цикл сообщений — до «Выход». Возвращается при выходе.
pub fn run(engine: Arc<Engine>, tray: bool, on_open: Box<dyn Fn() + Send + Sync>) {
    let _ = ENGINE.set(engine);
    let _ = ON_OPEN.set(on_open);
    unsafe {
        // просим Windows сообщать о выключении одними из первых
        SetProcessShutdownParameters(0x3FF, 0);
        let hinst = GetModuleHandleW(std::ptr::null());
        let cls = w("TuringMonitorRU-Core");
        let wc = WNDCLASSW {
            style: 0, lpfnWndProc: Some(wndproc), cbClsExtra: 0, cbWndExtra: 0, hInstance: hinst,
            hIcon: std::ptr::null_mut(), hCursor: std::ptr::null_mut(), hbrBackground: std::ptr::null_mut(),
            lpszMenuName: std::ptr::null(), lpszClassName: cls.as_ptr(),
        };
        RegisterClassW(&wc);
        // обычное (не message-only) невидимое окно — только такие получают WM_QUERYENDSESSION
        let hwnd = CreateWindowExW(0, cls.as_ptr(), w("Turing Monitor RU").as_ptr(), 0, 0, 0, 0, 0,
                                   std::ptr::null_mut(), std::ptr::null_mut(), hinst, std::ptr::null());
        HWND_MAIN.store(hwnd, std::sync::atomic::Ordering::SeqCst);
        RegisterPowerSettingNotification(hwnd, &GUID_CONSOLE_DISPLAY_STATE, 0);
        let mut nid: NOTIFYICONDATAW = std::mem::zeroed();
        if tray {
            nid.cbSize = std::mem::size_of::<NOTIFYICONDATAW>() as u32;
            nid.hWnd = hwnd;
            nid.uID = 1;
            nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
            nid.uCallbackMessage = WM_TRAY;
            // значок из ресурсов программы (id 1), иначе стандартный
            let ic = LoadIconW(hinst, 1 as _);
            nid.hIcon = if ic.is_null() { LoadIconW(std::ptr::null_mut(), IDI_APPLICATION) } else { ic };
            let tip = w("Turing Monitor RU");
            nid.szTip[..tip.len().min(127)].copy_from_slice(&tip[..tip.len().min(127)]);
            Shell_NotifyIconW(NIM_ADD, &nid);
        }
        info!("Окно сообщений Windows готово");
        let mut msg: MSG = std::mem::zeroed();
        while GetMessageW(&mut msg, std::ptr::null_mut(), 0, 0) > 0 {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        if tray {
            Shell_NotifyIconW(NIM_DELETE, &nid);
        }
    }
}
