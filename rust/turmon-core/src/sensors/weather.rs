//! Погода: Open-Meteo, запасные MET Norway и wttr.in; место — из настроек или по IP.

use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde_json::Value;

use super::Background;
use crate::values::{Val, Values};

const WIND_DIRS: [&str; 8] = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"];

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct City {
    pub name: String,
    pub lat: f64,
    pub lon: f64,
    #[serde(default)]
    pub region: String,
}

pub fn describe(code: i64) -> (&'static str, &'static str) {
    match code {
        0 => ("Ясно", "clear"),
        1 => ("Преимущественно ясно", "clear"),
        2 => ("Переменная облачность", "partly"),
        3 => ("Пасмурно", "cloudy"),
        45 => ("Туман", "fog"),
        48 => ("Изморозь", "fog"),
        51 => ("Слабая морось", "drizzle"),
        53 => ("Морось", "drizzle"),
        55 => ("Сильная морось", "drizzle"),
        56 | 57 => ("Ледяная морось", "drizzle"),
        61 => ("Небольшой дождь", "rain"),
        63 => ("Дождь", "rain"),
        65 => ("Ливень", "rain"),
        66 | 67 => ("Ледяной дождь", "rain"),
        71 => ("Небольшой снег", "snow"),
        73 => ("Снег", "snow"),
        75 => ("Сильный снег", "snow"),
        77 => ("Снежная крупа", "snow"),
        80 => ("Ливневый дождь", "rain"),
        81 => ("Ливни", "rain"),
        82 => ("Сильные ливни", "rain"),
        85 => ("Снегопад", "snow"),
        86 => ("Сильный снегопад", "snow"),
        95 => ("Гроза", "storm"),
        96 | 99 => ("Гроза с градом", "storm"),
        _ => ("—", "cloudy"),
    }
}

fn agent() -> ureq::Agent {
    ureq::Agent::config_builder().timeout_global(Some(Duration::from_secs(10))).build().into()
}

fn get(url: &str) -> anyhow::Result<Value> {
    let mut r = agent().get(url).header("User-Agent", "turing-monitor-ru").call()?;
    Ok(r.body_mut().read_json()?)
}

fn wind_dir(deg: Option<f64>) -> String {
    deg.map(|d| WIND_DIRS[(((d + 22.5).rem_euclid(360.0)) / 45.0) as usize % 8].to_string()).unwrap_or_default()
}

fn put(v: &mut Values, k: &str, x: Option<f64>) {
    if let Some(x) = x {
        v.insert(k.into(), Val::Num(x));
    }
}

fn open_meteo(lat: f64, lon: f64) -> anyhow::Result<Values> {
    let url = format!("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}\
        &current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,\
wind_direction_10m,is_day,surface_pressure&daily=temperature_2m_max,temperature_2m_min,weather_code\
&timezone=auto&wind_speed_unit=ms&forecast_days=3");
    let d = get(&url)?;
    let cur = &d["current"];
    let (desc, mut icon) = describe(cur["weather_code"].as_i64().unwrap_or(3));
    if icon == "clear" && cur["is_day"].as_i64() == Some(0) {
        icon = "night";
    }
    let mut v = Values::new();
    put(&mut v, "weather.temp", cur["temperature_2m"].as_f64());
    put(&mut v, "weather.feels", cur["apparent_temperature"].as_f64());
    put(&mut v, "weather.humidity", cur["relative_humidity_2m"].as_f64());
    put(&mut v, "weather.wind", cur["wind_speed_10m"].as_f64());
    v.insert("weather.wind_dir".into(), wind_dir(cur["wind_direction_10m"].as_f64()).into());
    put(&mut v, "weather.pressure", cur["surface_pressure"].as_f64().map(|p| p * 0.750062));
    v.insert("weather.desc".into(), desc.into());
    v.insert("weather.icon".into(), icon.into());
    let dl = &d["daily"];
    put(&mut v, "weather.max", dl["temperature_2m_max"][0].as_f64());
    put(&mut v, "weather.min", dl["temperature_2m_min"][0].as_f64());
    put(&mut v, "weather.tomorrow_max", dl["temperature_2m_max"][1].as_f64());
    put(&mut v, "weather.tomorrow_min", dl["temperature_2m_min"][1].as_f64());
    if let Some(c) = dl["weather_code"][1].as_i64() {
        let (d2, i2) = describe(c);
        v.insert("weather.tomorrow_desc".into(), d2.into());
        v.insert("weather.tomorrow_icon".into(), i2.into());
    }
    Ok(v)
}

fn met_symbol(code: &str) -> (&'static str, &'static str) {
    const M: [(&str, &str, &str); 11] = [
        ("thunder", "Гроза", "storm"), ("sleet", "Мокрый снег", "snow"), ("snow", "Снег", "snow"),
        ("heavyrain", "Ливень", "rain"), ("lightrain", "Небольшой дождь", "rain"), ("rain", "Дождь", "rain"),
        ("fog", "Туман", "fog"), ("partlycloudy", "Переменная облачность", "partly"),
        ("fair", "Преимущественно ясно", "clear"), ("clearsky", "Ясно", "clear"), ("cloudy", "Пасмурно", "cloudy"),
    ];
    for (k, d, i) in M {
        if code.starts_with(k) {
            return (d, if i == "clear" && code.ends_with("_night") { "night" } else { i });
        }
    }
    ("—", "cloudy")
}

fn feels(t: f64, wind: Option<f64>) -> f64 {
    match wind {
        Some(w) if t <= 10.0 && w >= 1.4 => {
            let k = (w * 3.6).powf(0.16);
            13.12 + 0.6215 * t - 11.37 * k + 0.3965 * t * k
        }
        _ => t,
    }
}

fn met_no(lat: f64, lon: f64) -> anyhow::Result<Values> {
    let url = format!("https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat:.3}&lon={lon:.3}");
    let mut r = agent().get(&url).header("User-Agent", "turing-monitor-ru/1.0 github.com/vyalu/turing-monitor-ru").call()?;
    let d: Value = r.body_mut().read_json()?;
    let ts = d["properties"]["timeseries"].as_array().ok_or_else(|| anyhow::anyhow!("нет данных"))?;
    let now = &ts[0]["data"];
    let det = &now["instant"]["details"];
    let sym = now["next_1_hours"]["summary"]["symbol_code"].as_str()
        .or(now["next_6_hours"]["summary"]["symbol_code"].as_str()).unwrap_or("");
    let (desc, icon) = met_symbol(sym);
    let t = det["air_temperature"].as_f64();
    let wind = det["wind_speed"].as_f64();
    let mut v = Values::new();
    put(&mut v, "weather.temp", t);
    put(&mut v, "weather.feels", t.map(|t| feels(t, wind)));
    put(&mut v, "weather.humidity", det["relative_humidity"].as_f64());
    put(&mut v, "weather.wind", wind);
    v.insert("weather.wind_dir".into(), wind_dir(det["wind_from_direction"].as_f64()).into());
    put(&mut v, "weather.pressure", det["air_pressure_at_sea_level"].as_f64().map(|p| p * 0.750062));
    v.insert("weather.desc".into(), desc.into());
    v.insert("weather.icon".into(), icon.into());
    let temps: Vec<f64> = ts.iter().take(49).filter_map(|x| x["data"]["instant"]["details"]["air_temperature"].as_f64()).collect();
    let mm = |s: &[f64]| (s.iter().cloned().fold(f64::MIN, f64::max), s.iter().cloned().fold(f64::MAX, f64::min));
    if temps.len() >= 24 {
        let (mx, mn) = mm(&temps[..24]);
        put(&mut v, "weather.max", Some(mx));
        put(&mut v, "weather.min", Some(mn));
    }
    if temps.len() > 25 {
        let (mx, mn) = mm(&temps[24..]);
        put(&mut v, "weather.tomorrow_max", Some(mx));
        put(&mut v, "weather.tomorrow_min", Some(mn));
        let mid = &ts[36.min(ts.len() - 1)]["data"];
        let s2 = mid["next_6_hours"]["summary"]["symbol_code"].as_str()
            .or(mid["next_1_hours"]["summary"]["symbol_code"].as_str()).unwrap_or("").replace("_night", "_day");
        let (d2, i2) = met_symbol(&s2);
        v.insert("weather.tomorrow_desc".into(), d2.into());
        v.insert("weather.tomorrow_icon".into(), i2.into());
    }
    Ok(v)
}

fn wwo(code: i64) -> (&'static str, &'static str) {
    match code {
        113 => ("Ясно", "clear"),
        116 => ("Переменная облачность", "partly"),
        119 | 122 => ("Пасмурно", "cloudy"),
        143 | 248 | 260 => ("Туман", "fog"),
        200 | 386 | 389 | 392 | 395 => ("Гроза", "storm"),
        179 | 182 | 185 | 227 | 230 | 281 | 284 | 311 | 314 | 317 | 320 | 323 | 326 | 329 | 332 | 335 | 338 | 350
        | 362 | 365 | 368 | 371 | 374 | 377 => ("Снег", "snow"),
        263 | 266 => ("Морось", "drizzle"),
        _ => ("Дождь", "rain"),
    }
}

fn wttr(lat: f64, lon: f64) -> anyhow::Result<Values> {
    let d = get(&format!("https://wttr.in/{lat:.3},{lon:.3}?format=j1&lang=ru"))?;
    let cur = &d["current_condition"][0];
    let f = |k: &str| cur[k].as_str().and_then(|s| s.parse::<f64>().ok());
    let (desc, icon) = wwo(cur["weatherCode"].as_str().and_then(|s| s.parse().ok()).unwrap_or(119));
    let ru = cur["lang_ru"][0]["value"].as_str().map(|s| {
        let s = s.trim();
        let mut c = s.chars();
        c.next().map(|f| f.to_uppercase().collect::<String>() + &c.as_str().to_lowercase()).unwrap_or_default()
    });
    let mut v = Values::new();
    put(&mut v, "weather.temp", f("temp_C"));
    put(&mut v, "weather.feels", f("FeelsLikeC"));
    put(&mut v, "weather.humidity", f("humidity"));
    put(&mut v, "weather.wind", f("windspeedKmph").map(|w| w / 3.6));
    v.insert("weather.wind_dir".into(), wind_dir(f("winddirDegree")).into());
    put(&mut v, "weather.pressure", f("pressure").map(|p| p * 0.750062));
    v.insert("weather.desc".into(), ru.filter(|s| !s.is_empty()).unwrap_or(desc.into()).into());
    v.insert("weather.icon".into(), icon.into());
    let day = |i: usize, k: &str| d["weather"][i][k].as_str().and_then(|s| s.parse::<f64>().ok());
    put(&mut v, "weather.max", day(0, "maxtempC"));
    put(&mut v, "weather.min", day(0, "mintempC"));
    put(&mut v, "weather.tomorrow_max", day(1, "maxtempC"));
    put(&mut v, "weather.tomorrow_min", day(1, "mintempC"));
    if let Some(c) = d["weather"][1]["hourly"][4]["weatherCode"].as_str().and_then(|s| s.parse().ok()) {
        let (d2, i2) = wwo(c);
        v.insert("weather.tomorrow_desc".into(), d2.into());
        v.insert("weather.tomorrow_icon".into(), i2.into());
    }
    Ok(v)
}

type Source = (&'static str, fn(f64, f64) -> anyhow::Result<Values>);
pub const SOURCES: [Source; 3] = [("open-meteo.com", open_meteo), ("met.no", met_no), ("wttr.in", wttr)];

fn locate_by_ip() -> anyhow::Result<City> {
    let mut errors = vec![];
    let parsers: [(&str, fn(&Value) -> Option<City>); 4] = [
        ("https://ipwho.is/?lang=ru&fields=success,city,region,country,latitude,longitude", |d| {
            d["success"].as_bool().filter(|s| *s)?;
            Some(City { name: d["city"].as_str()?.into(), lat: d["latitude"].as_f64()?, lon: d["longitude"].as_f64()?,
                        region: d["country"].as_str().unwrap_or("").into() })
        }),
        ("https://ipinfo.io/json", |d| {
            let (a, b) = d["loc"].as_str()?.split_once(',')?;
            Some(City { name: d["city"].as_str().unwrap_or("").into(), lat: a.parse().ok()?, lon: b.parse().ok()?,
                        region: d["country"].as_str().unwrap_or("").into() })
        }),
        ("https://get.geojs.io/v1/ip/geo.json", |d| {
            Some(City { name: d["city"].as_str().unwrap_or("").into(),
                        lat: d["latitude"].as_str()?.parse().ok()?, lon: d["longitude"].as_str()?.parse().ok()?,
                        region: d["country"].as_str().unwrap_or("").into() })
        }),
        ("https://ipapi.co/json/", |d| {
            Some(City { name: d["city"].as_str().unwrap_or("").into(), lat: d["latitude"].as_f64()?,
                        lon: d["longitude"].as_f64()?, region: d["country_name"].as_str().unwrap_or("").into() })
        }),
    ];
    for (url, parse) in parsers {
        match get(url) {
            Ok(d) => match parse(&d) {
                Some(c) => return Ok(c),
                None => errors.push(format!("{url}: нет данных")),
            },
            Err(e) => errors.push(format!("{url}: {e}")),
        }
    }
    anyhow::bail!("не удалось определить место по IP ({})", errors.join("; "))
}

/// Погода в фоне: раз в 15 минут. `city` — выбранный в настройках город (иначе — по IP).
pub fn provider(city: Option<City>, auto: bool, cache: PathBuf) -> (Background, Arc<Mutex<String>>) {
    let source = Arc::new(Mutex::new(String::new()));
    let s2 = source.clone();
    let mut located: Option<City> = None;
    let bg = Background::spawn("Погода", Duration::from_secs(15 * 60), move || {
        let c = match &city {
            Some(c) => c.clone(),
            None => {
                if !auto {
                    return Ok(Values::new());
                }
                if located.is_none() {
                    located = match locate_by_ip() {
                        Ok(c) => {
                            let _ = std::fs::write(&cache, serde_json::to_string(&c).unwrap_or_default());
                            Some(c)
                        }
                        Err(e) => match std::fs::read_to_string(&cache).ok().and_then(|t| serde_json::from_str(&t).ok()) {
                            Some(c) => Some(c),
                            None => return Err(e),
                        },
                    };
                }
                located.clone().unwrap()
            }
        };
        let last = s2.lock().unwrap().clone();
        let mut order: Vec<&Source> = SOURCES.iter().collect();
        order.sort_by_key(|(n, _)| *n != last);
        let mut errors = vec![];
        for (name, f) in order {
            match f(c.lat, c.lon) {
                Ok(mut v) if v.contains_key("weather.temp") => {
                    *s2.lock().unwrap() = name.to_string();
                    v.insert("weather.city".into(), c.name.clone().into());
                    return Ok(v);
                }
                Ok(_) => errors.push(format!("{name}: нет данных")),
                Err(e) => errors.push(format!("{name}: {e}")),
            }
        }
        anyhow::bail!("сервисы погоды недоступны ({})", errors.join("; "))
    });
    (bg, source)
}
