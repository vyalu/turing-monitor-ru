//! Мелочи, зависящие от системы.

#[cfg(windows)]
mod imp {
    use std::sync::atomic::{AtomicBool, Ordering};

    static ON: AtomicBool = AtomicBool::new(false);

    #[link(name = "winmm")]
    unsafe extern "system" {
        fn timeBeginPeriod(p: u32) -> u32;
        fn timeEndPeriod(p: u32) -> u32;
    }

    /// Точный системный таймер (1 мс) на время анимации — иначе кадры идут неровно.
    pub fn precise_timer(on: bool) {
        if ON.swap(on, Ordering::SeqCst) != on {
            unsafe {
                if on { timeBeginPeriod(1) } else { timeEndPeriod(1) };
            }
        }
    }

    pub fn is_admin() -> bool {
        #[link(name = "shell32")]
        unsafe extern "system" {
            fn IsUserAnAdmin() -> i32;
        }
        unsafe { IsUserAnAdmin() != 0 }
    }
}

#[cfg(not(windows))]
mod imp {
    pub fn precise_timer(_on: bool) {}
    pub fn is_admin() -> bool {
        false
    }
}

pub use imp::*;
