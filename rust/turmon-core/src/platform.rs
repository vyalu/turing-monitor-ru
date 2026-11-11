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

    /// Дочерний процесс закроется вместе с программой, даже если её завершат принудительно.
    pub fn kill_with_parent(child: &std::process::Child) {
        use std::os::windows::io::AsRawHandle;
        use std::sync::OnceLock;
        use windows_sys::Win32::System::JobObjects::*;
        static JOB: OnceLock<usize> = OnceLock::new();
        unsafe {
            let job = *JOB.get_or_init(|| {
                let j = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                SetInformationJobObject(j, JobObjectExtendedLimitInformation, &info as *const _ as _,
                                        std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32);
                j as usize
            });
            AssignProcessToJobObject(job as _, child.as_raw_handle() as _);
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
    pub fn kill_with_parent(_c: &std::process::Child) {}
    pub fn is_admin() -> bool {
        false
    }
}

pub use imp::*;
