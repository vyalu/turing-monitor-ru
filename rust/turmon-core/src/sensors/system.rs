//! Процессор, память, диск, сеть, время работы — через sysinfo.

use std::time::Instant;

use sysinfo::{CpuRefreshKind, Disks, MemoryRefreshKind, Networks, RefreshKind, System};

use super::Provider;
use crate::values::{Val, Values};

pub fn short_cpu_name(name: &str) -> String {
    let mut n = name.to_string();
    for junk in ["(R)", "(TM)", "(tm)", "CPU", "Processor", "with Radeon Graphics"] {
        n = n.replace(junk, " ");
    }
    let mut parts: Vec<&str> = n.split_whitespace()
        .filter(|p| !p.ends_with("-Core") && !matches!(*p, "AMD" | "Intel" | "@")).collect();
    if name.contains('@') {
        parts.retain(|p| !p.ends_with("GHz"));
    }
    let s = parts.into_iter().take(4).collect::<Vec<_>>().join(" ");
    if s.is_empty() { name.to_string() } else { s }
}

pub struct SystemProvider {
    sys: System,
    disks: Option<Disks>,
    nets: Option<Networks>,
    pub net_iface: String,
    pub disk: String,
    last: Instant,
    procs_at: Option<Instant>,
    procs: usize,
    cpu_name: String,
}

impl SystemProvider {
    pub fn new(net_iface: &str, disk: &str) -> SystemProvider {
        let sys = System::new_with_specifics(RefreshKind::nothing()
            .with_cpu(CpuRefreshKind::everything()).with_memory(MemoryRefreshKind::everything()))
            .unwrap_or_else(|_| System::new().expect("sysinfo"));
        let cpu_name = sys.cpus().first().map(|c| c.brand().trim().to_string()).unwrap_or_else(|| "CPU".into());
        let disk = if disk.is_empty() {
            if cfg!(windows) { format!("{}\\", std::env::var("SystemDrive").unwrap_or("C:".into())) } else { "/".into() }
        } else {
            disk.into()
        };
        SystemProvider { sys, disks: Disks::new_with_refreshed_list().ok(), nets: Networks::new_with_refreshed_list().ok(),
                         net_iface: net_iface.into(), disk, last: Instant::now(), procs_at: None, procs: 0, cpu_name }
    }
}

impl Provider for SystemProvider {
    fn name(&self) -> &str {
        "Система"
    }

    fn update(&mut self, v: &mut Values) -> anyhow::Result<()> {
        let dt = self.last.elapsed().as_secs_f64().max(1e-3);
        self.last = Instant::now();
        self.sys.refresh_cpu_all();
        self.sys.refresh_memory();
        v.insert("cpu.load".into(), Val::Num(self.sys.global_cpu_usage() as f64));
        for (i, c) in self.sys.cpus().iter().enumerate() {
            v.insert(format!("cpu.core{}.load", i + 1), Val::Num(c.usage() as f64));
        }
        v.insert("cpu.cores".into(), Val::Int(self.sys.cpus().len() as i64));
        v.insert("cpu.name".into(), short_cpu_name(&self.cpu_name).into());
        v.insert("cpu.fullname".into(), self.cpu_name.clone().into());
        let freq: Vec<u64> = self.sys.cpus().iter().map(|c| c.frequency()).filter(|f| *f > 0).collect();
        if !freq.is_empty() {
            v.insert("cpu.freq".into(), Val::Num(freq.iter().sum::<u64>() as f64 / freq.len() as f64 / 1000.0));
        }
        let (total, avail) = (self.sys.total_memory() as f64, self.sys.available_memory() as f64);
        const GB: f64 = 1073741824.0;
        if total > 0.0 {
            v.insert("ram.load".into(), Val::Num((total - avail) / total * 100.0));
            v.insert("ram.used".into(), Val::Num((total - avail) / GB));
            v.insert("ram.used_mb".into(), Val::Num((total - avail) / 1048576.0));
            v.insert("ram.free".into(), Val::Num(avail / GB));
            v.insert("ram.total".into(), Val::Num(total / GB));
        }
        if let Some(disks) = self.disks.as_mut() {
            disks.refresh(false);
            let want = self.disk.trim_end_matches(['\\', '/']).to_lowercase();
            let pick = disks.iter().find(|d| {
                d.mount_point().to_string_lossy().trim_end_matches(['\\', '/']).to_lowercase() == want
            }).or_else(|| disks.iter().next());
            if let Some(d) = pick {
                let (t, a) = (d.total_space() as f64, d.available_space() as f64);
                if t > 0.0 {
                    v.insert("disk.load".into(), Val::Num((t - a) / t * 100.0));
                    v.insert("disk.used".into(), Val::Num((t - a) / GB));
                    v.insert("disk.free".into(), Val::Num(a / GB));
                    v.insert("disk.total".into(), Val::Num(t / GB));
                }
                let u = d.usage();
                v.insert("disk.read".into(), Val::Num(u.read_bytes as f64 / dt / 1048576.0));
                v.insert("disk.write".into(), Val::Num(u.written_bytes as f64 / dt / 1048576.0));
            }
        }
        let (mut rx, mut tx, mut trx, mut ttx) = (0u64, 0u64, 0u64, 0u64);
        if let Some(nets) = self.nets.as_mut() {
            nets.refresh(true);
            for (name, n) in nets.iter() {
                if !self.net_iface.is_empty() && name.to_string_lossy() != self.net_iface.as_str() {
                    continue;
                }
                rx += n.received();
                tx += n.transmitted();
                trx += n.total_received();
                ttx += n.total_transmitted();
            }
        }
        v.insert("net.down".into(), Val::Num(rx as f64 / dt / 1048576.0));
        v.insert("net.up".into(), Val::Num(tx as f64 / dt / 1048576.0));
        v.insert("net.total_down".into(), Val::Num(trx as f64 / GB));
        v.insert("net.total_up".into(), Val::Num(ttx as f64 / GB));
        v.insert("sys.uptime".into(), Val::Num(System::uptime().unwrap_or(0) as f64));
        // список процессов — недёшево, раз в 10 с
        if self.procs_at.is_none_or(|t| t.elapsed().as_secs() >= 10) {
            self.sys.refresh_processes(sysinfo::ProcessesToUpdate::All, true);
            self.procs = self.sys.processes().len();
            self.procs_at = Some(Instant::now());
        }
        v.insert("sys.processes".into(), Val::Int(self.procs as i64));
        Ok(())
    }
}
