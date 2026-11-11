//! Громкость системы (Windows Core Audio).

#[cfg(windows)]
use super::Provider;
#[cfg(windows)]
use crate::values::{Val, Values};

#[cfg(windows)]
pub struct VolumeProvider {
    ep: Option<windows::Win32::Media::Audio::Endpoints::IAudioEndpointVolume>,
}

#[cfg(windows)]
impl VolumeProvider {
    pub fn new() -> Self {
        VolumeProvider { ep: None }
    }

    fn endpoint(&mut self) -> anyhow::Result<&windows::Win32::Media::Audio::Endpoints::IAudioEndpointVolume> {
        use windows::Win32::Media::Audio::*;
        use windows::Win32::System::Com::*;
        if self.ep.is_none() {
            unsafe {
                // поток датчиков: COM инициализируем один раз (повторный вызов безвреден)
                let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
                let en: IMMDeviceEnumerator = CoCreateInstance(&MMDeviceEnumerator, None, CLSCTX_ALL)?;
                let dev = en.GetDefaultAudioEndpoint(eRender, eMultimedia)?;
                self.ep = Some(dev.Activate(CLSCTX_ALL, None)?);
            }
        }
        Ok(self.ep.as_ref().unwrap())
    }
}

#[cfg(windows)]
impl Provider for VolumeProvider {
    fn name(&self) -> &str {
        "Громкость"
    }

    fn update(&mut self, v: &mut Values) -> anyhow::Result<()> {
        let r = (|| unsafe {
            let ep = self.endpoint()?;
            let vol = ep.GetMasterVolumeLevelScalar()?;
            let mute = ep.GetMute()?.as_bool();
            Ok::<_, anyhow::Error>((vol, mute))
        })();
        match r {
            Ok((vol, mute)) => {
                v.insert("sys.volume".into(), Val::Int((vol * 100.0).round() as i64));
                v.insert("sys.mute".into(), Val::Int(mute as i64));
                Ok(())
            }
            Err(e) => {
                self.ep = None; // устройство сменилось — найдём заново
                Err(e)
            }
        }
    }
}
