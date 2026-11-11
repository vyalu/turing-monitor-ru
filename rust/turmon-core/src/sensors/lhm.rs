//! Температуры, частоты, вентиляторы и видеокарта — через LibreHardwareMonitor.
//!
//! Библиотека написана на .NET, поэтому её опрашивает маленькая программа lhm-host.exe
//! (лежит в папке lhm рядом с программой): на строку «u» она отвечает строкой JSON со всеми
//! датчиками. Права администратора она получает от нашей программы.

use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::{Arc, Mutex};

use serde::Deserialize;

use super::Provider;
use crate::values::{Val, Values};

#[derive(Clone, Debug, Deserialize)]
pub struct Sensor {
    /// Идентификатор LHM: «/amdcpu/0/temperature/2»
    #[serde(rename = "i")]
    pub ident: String,
    #[serde(rename = "h")]
    pub hardware: String,
    #[serde(rename = "t")]
    pub hw_type: String,
    #[serde(rename = "k")]
    pub kind: String,
    #[serde(rename = "n")]
    pub name: String,
    #[serde(rename = "v")]
    pub value: Option<f64>,
}

impl Sensor {
    pub fn label(&self) -> String {
        format!("{} → {} ({})", self.hardware, self.name, self.kind)
    }
}

pub const CPU_TEMP_NAMES: [&str; 9] = ["CPU Package", "Core (Tctl/Tdie)", "Core (Tctl)", "Tctl/Tdie", "Core Max",
    "Core Average", "CCD1 (Tdie)", "CPU Core", "Core #1"];
const GPU_KINDS: [&str; 3] = ["GpuNvidia", "GpuAmd", "GpuIntel"];

pub fn lhm_dir() -> PathBuf {
    let mut c = vec![];
    if let Ok(exe) = std::env::current_exe() {
        if let Some(d) = exe.parent() {
            c.push(d.join("lhm"));
        }
    }
    c.push(PathBuf::from("lhm"));
    c.into_iter().find(|p| p.join("lhm-host.exe").exists()).unwrap_or_else(|| PathBuf::from("lhm"))
}

struct Host {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

pub struct LhmProvider {
    pub overrides: HashMap<String, String>,
    pub disk_index: usize,
    host: Option<Host>,
    /// Последний замер — для окна настроек (выбор датчиков) без нового опроса железа.
    pub last: Arc<Mutex<Vec<Sensor>>>,
    status: String,
}

impl LhmProvider {
    pub fn new(overrides: HashMap<String, String>, disk_index: usize) -> LhmProvider {
        LhmProvider { overrides, disk_index, host: None, last: Arc::new(Mutex::new(vec![])), status: String::new() }
    }

    fn query(&mut self) -> anyhow::Result<Vec<Sensor>> {
        let h = self.host.as_mut().ok_or_else(|| anyhow::anyhow!("не запущен"))?;
        h.stdin.write_all(b"u\n")?;
        h.stdin.flush()?;
        let mut line = String::new();
        if h.stdout.read_line(&mut line)? == 0 {
            self.host = None;
            anyhow::bail!("lhm-host завершился");
        }
        Ok(serde_json::from_str(&line)?)
    }
}

/// Перевести датчики LHM в показатели программы (как в Python-версии).
pub fn map_sensors(all: &[Sensor], overrides: &HashMap<String, String>, disk_index: usize, v: &mut Values) {
    let pick = |types: &[&str], kind: &str, names: Option<&[&str]>, contains: Option<&str>| -> Option<f64> {
        all.iter().find(|s| {
            types.contains(&s.hw_type.as_str()) && s.kind == kind && s.value.is_some()
                && names.is_none_or(|n| n.contains(&s.name.as_str()))
                && contains.is_none_or(|c| s.name.to_lowercase().contains(&c.to_lowercase()))
        }).and_then(|s| s.value)
    };
    let pick_ordered = |types: &[&str], kind: &str, names: &[&str]| -> Option<f64> {
        names.iter().find_map(|n| pick(types, kind, Some(&[n]), None))
    };
    let mut put = |k: &str, x: Option<f64>| {
        if let Some(x) = x {
            v.insert(k.into(), Val::Num(x));
        }
    };
    let cpu = ["Cpu"];
    let t = pick_ordered(&cpu, "Temperature", &CPU_TEMP_NAMES).or_else(|| pick(&cpu, "Temperature", None, None));
    put("cpu.temp", t.filter(|x| *x != 0.0));
    let clocks: Vec<f64> = all.iter().filter(|s| s.hw_type == "Cpu" && s.kind == "Clock" && s.name.starts_with("Core #"))
        .filter_map(|s| s.value).filter(|x| *x != 0.0).collect();
    if !clocks.is_empty() {
        put("cpu.freq", Some(clocks.iter().sum::<f64>() / clocks.len() as f64 / 1000.0));
        put("cpu.freq_max", Some(clocks.iter().cloned().fold(f64::MIN, f64::max) / 1000.0));
    }
    put("cpu.power", pick_ordered(&cpu, "Power", &["Package", "CPU Package", "Cores"]));
    put("cpu.voltage", pick(&cpu, "Voltage", None, Some("Core")));
    let fans: Vec<&Sensor> = all.iter().filter(|s| s.hw_type == "Motherboard" && s.kind == "Fan"
        && s.value.is_some_and(|x| x != 0.0)).collect();
    let cpu_fan = fans.iter().find(|s| s.name.to_lowercase().contains("cpu")).or(fans.first()).and_then(|s| s.value);
    put("cpu.fan", cpu_fan);
    put("cpu.pump", fans.iter().find(|s| { let n = s.name.to_lowercase(); n.contains("pump") || n.contains("aio") })
        .and_then(|s| s.value));
    put("mb.temp", pick(&["Motherboard"], "Temperature", None, None));
    // видеокарта: дискретная важнее встроенной
    if let Some(gt) = GPU_KINDS.iter().find(|g| all.iter().any(|s| s.hw_type == **g)) {
        let g = [*gt];
        let name = all.iter().find(|s| s.hw_type == *gt).map(|s| s.hardware.clone()).unwrap_or_default();
        let short = name.replace("NVIDIA ", "").replace("GeForce ", "").replace("AMD ", "");
        put("gpu.temp", pick_ordered(&g, "Temperature", &["GPU Core", "GPU Hot Spot"]));
        put("gpu.hotspot", pick(&g, "Temperature", Some(&["GPU Hot Spot"]), None));
        put("gpu.load", pick_ordered(&g, "Load", &["GPU Core", "D3D 3D"]));
        put("gpu.freq", pick(&g, "Clock", Some(&["GPU Core"]), None));
        put("gpu.mem_freq", pick(&g, "Clock", Some(&["GPU Memory"]), None));
        put("gpu.power", pick_ordered(&g, "Power", &["GPU Package", "GPU Power", "GPU Core"]));
        put("gpu.fan", pick(&g, "Fan", None, None));
        put("gpu.fan_load", pick(&g, "Control", None, None));
        let used = pick_ordered(&g, "SmallData", &["GPU Memory Used", "D3D Dedicated Memory Used"]);
        let total = pick(&g, "SmallData", Some(&["GPU Memory Total"]), None);
        let mut mem_load = pick(&g, "Load", Some(&["GPU Memory"]), None);
        if let Some(u) = used {
            put("gpu.mem_used_mb", Some(u));
            put("gpu.mem_used", Some(u / 1024.0));
            if mem_load.is_none() {
                mem_load = total.filter(|t| *t > 0.0).map(|t| u / t * 100.0);
            }
        }
        put("gpu.mem_total_mb", total);
        put("gpu.mem_load", mem_load);
        v.insert("gpu.name".into(), Val::Str(short));
    }
    // накопитель
    let mut storages: Vec<&str> = vec![];
    for s in all.iter().filter(|s| s.hw_type == "Storage") {
        if !storages.contains(&s.hardware.as_str()) {
            storages.push(&s.hardware);
        }
    }
    if !storages.is_empty() {
        let hw = storages[disk_index.min(storages.len() - 1)];
        let dt = all.iter().find(|s| s.hardware == hw && s.kind == "Temperature" && s.value.is_some_and(|x| x != 0.0))
            .and_then(|s| s.value);
        if let Some(d) = dt {
            v.insert("disk.temp".into(), Val::Num(d));
        }
        v.insert("disk.name".into(), Val::Str(hw.to_string()));
    }
    // ручные привязки из настроек
    for (key, ident) in overrides {
        if let Some(x) = all.iter().find(|s| &s.ident == ident).and_then(|s| s.value) {
            v.insert(key.clone(), Val::Num(x));
        }
    }
}

impl Provider for LhmProvider {
    fn name(&self) -> &str {
        "LibreHardwareMonitor"
    }

    fn start(&mut self) -> anyhow::Result<()> {
        let exe = lhm_dir().join("lhm-host.exe");
        if !exe.exists() {
            anyhow::bail!("не найден {}", exe.display());
        }
        let mut cmd = Command::new(&exe);
        cmd.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x0800_0000); // без окна консоли
        }
        let mut child = cmd.spawn()?;
        crate::platform::kill_with_parent(&child);
        let stdin = child.stdin.take().unwrap();
        let stdout = BufReader::new(child.stdout.take().unwrap());
        self.host = Some(Host { child, stdin, stdout });
        let first = self.query()?;
        log::info!("LibreHardwareMonitor: датчиков {}", first.len());
        *self.last.lock().unwrap() = first;
        Ok(())
    }

    fn update(&mut self, v: &mut Values) -> anyhow::Result<()> {
        if self.host.is_none() {
            // упал — пробуем перезапустить
            self.start()?;
        }
        let all = self.query()?;
        map_sensors(&all, &self.overrides, self.disk_index, v);
        *self.last.lock().unwrap() = all;
        Ok(())
    }

    fn stop(&mut self) {
        if let Some(mut h) = self.host.take() {
            let _ = h.stdin.write_all(b"q\n");
            let _ = h.child.kill();
        }
    }

    fn status(&self) -> String {
        self.status.clone()
    }
}

impl Drop for LhmProvider {
    fn drop(&mut self) {
        self.stop();
    }
}
