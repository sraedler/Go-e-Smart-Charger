import http.server
import socketserver
import urllib.request
import urllib.parse
import json
import ssl
import os
import time
import threading
from datetime import datetime, timedelta

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
CERT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs")
SERVER_CRT = os.path.join(CERT_DIR, "fullchain.crt") if os.path.exists(os.path.join(CERT_DIR, "fullchain.crt")) else os.path.join(CERT_DIR, "server.crt")
SERVER_KEY = os.path.join(CERT_DIR, "server.key")

# Global state
config_lock = threading.RLock()
state_lock = threading.RLock()
savings_lock = threading.RLock()

default_config = {
    "goe_ip": "192.168.100.67",
    "solaredge_api_key": "UAE8KFFWY50TYUBLMLHASRBYHI965DC1",
    "solaredge_site_id": "4353282",
    "mode": "pv",
    "pv_threshold_watt": 0,
    "normal_ampere": 16,
    "min_pv_ampere": 6,
    "max_pv_ampere": 16,
    "solaredge_poll_seconds": 180,
    "phases_setting": "auto", # auto, 1, 3
    "server_port": 2009,
    "midnight_reset": True,
    "auto_wakeup": True,
    "off_delay_seconds": 180,
    "min_pause_seconds": 120,
    "enable_smoothing": True,
    "pause_until": ""
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(default_config)
        return default_config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # Merge missing keys
            for k, v in default_config.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    except Exception as e:
        print(f"[Config] Error loading config: {e}")
        return default_config

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[Config] Error saving config: {e}")

global_config = load_config()

# --- PV Charging Savings & Statistics Tracker ---
SAVINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "savings.json")
savings_lock = threading.Lock()

def load_savings():
    if not os.path.exists(SAVINGS_FILE):
        default_stats = {
            "grid_price_ct": 30.0,
            "feedin_price_ct": 7.0,
            "total_pv_kwh": 0.0,
            "total_grid_kwh": 0.0,
            "start_date": datetime.now().strftime("%Y-%m-%d"),
            "daily": {}
        }
        save_savings(default_stats)
        return default_stats
    try:
        with open(SAVINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "daily" not in data:
                data["daily"] = {}
            if "start_date" not in data or not data["start_date"]:
                dates = sorted(data["daily"].keys()) if data["daily"] else []
                data["start_date"] = dates[0] if dates else datetime.now().strftime("%Y-%m-%d")
            return data
    except Exception as e:
        print(f"[Savings] Error loading savings data: {e}")
        return {
            "grid_price_ct": 30.0,
            "feedin_price_ct": 7.0,
            "total_pv_kwh": 0.0,
            "total_grid_kwh": 0.0,
            "start_date": datetime.now().strftime("%Y-%m-%d"),
            "daily": {}
        }

def save_savings(savings_data):
    try:
        with open(SAVINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(savings_data, f, indent=2)
    except Exception as e:
        print(f"[Savings] Error saving data: {e}")

global_savings = load_savings()

def get_savings_summary():
    with state_lock:
        vkw_live_price = system_status.get("vkw_tariff", {}).get("current_price_ct", None)
    
    with savings_lock:
        grid_price = float(global_savings.get("grid_price_ct", 30.0))
        if vkw_live_price is not None and vkw_live_price != 0.0:
            feedin_price = float(vkw_live_price)
            global_savings["feedin_price_ct"] = round(feedin_price, 2)
        else:
            feedin_price = float(global_savings.get("feedin_price_ct", 7.0))
        total_pv = float(global_savings.get("total_pv_kwh", 0.0))
        total_grid = float(global_savings.get("total_grid_kwh", 0.0))
        daily = dict(global_savings.get("daily", {}))

    total_charged = total_pv + total_grid
    autarky_pct = round((total_pv / total_charged * 100.0), 1) if total_charged > 0 else 100.0
    
    saving_per_kwh_eur = max(0.0, (grid_price - feedin_price) / 100.0)
    total_savings_eur = round(total_pv * saving_per_kwh_eur, 2)
    co2_saved_kg = round(total_pv * 0.40, 1)

    # Actual charging cost calculation (PV energy at opportunity cost feedin_price, Grid energy at grid_price)
    total_charging_cost_eur = round((total_pv * (feedin_price / 100.0)) + (total_grid * (grid_price / 100.0)), 2)
    effective_price_ct_kwh = round((total_charging_cost_eur * 100.0 / total_charged), 1) if total_charged > 0 else grid_price

    today_str = datetime.now().strftime("%Y-%m-%d")
    today_data = daily.get(today_str, {"pv_kwh": 0.0, "grid_kwh": 0.0})
    today_pv = round(float(today_data.get("pv_kwh", 0.0)), 2)
    today_grid = round(float(today_data.get("grid_kwh", 0.0)), 2)
    today_charged = today_pv + today_grid
    today_autarky = round((today_pv / today_charged * 100.0), 1) if today_charged > 0 else 100.0
    today_savings_eur = round(today_pv * saving_per_kwh_eur, 2)
    today_charging_cost_eur = round((today_pv * (feedin_price / 100.0)) + (today_grid * (grid_price / 100.0)), 2)
    today_effective_price_ct_kwh = round((today_charging_cost_eur * 100.0 / today_charged), 1) if today_charged > 0 else grid_price

    all_dates = sorted(daily.keys()) if daily else []
    with savings_lock:
        start_date_iso = global_savings.get("start_date")
        if not start_date_iso:
            start_date_iso = all_dates[0] if all_dates else today_str
            global_savings["start_date"] = start_date_iso

    try:
        dt_start = datetime.strptime(start_date_iso, "%Y-%m-%d")
        dt_end = datetime.strptime(today_str, "%Y-%m-%d")
        start_fmt = dt_start.strftime("%d.%m.%Y")
        end_fmt = dt_end.strftime("%d.%m.%Y")
        if start_date_iso == today_str:
            period_str = f"Seit heute ({start_fmt})"
        else:
            period_str = f"{start_fmt} – {end_fmt}"
    except Exception:
        period_str = f"Seit {start_date_iso}"
        start_fmt = start_date_iso
        end_fmt = today_str

    daily_history = []
    sorted_dates = sorted(daily.keys())[-14:]
    for d in sorted_dates:
        item = daily[d]
        pv_k = round(float(item.get("pv_kwh", 0.0)), 2)
        gr_k = round(float(item.get("grid_kwh", 0.0)), 2)
        tot_k = pv_k + gr_k
        aut = round((pv_k / tot_k * 100.0), 1) if tot_k > 0 else 100.0
        sav_eur = round(pv_k * saving_per_kwh_eur, 2)
        d_cost_eur = round((pv_k * (feedin_price / 100.0)) + (gr_k * (grid_price / 100.0)), 2)
        d_effective_price_ct = round((d_cost_eur * 100.0 / tot_k), 1) if tot_k > 0 else grid_price
        
        try:
            dt_obj = datetime.strptime(d, "%Y-%m-%d")
            fmt_date = dt_obj.strftime("%d.%m.")
        except Exception:
            fmt_date = d

        daily_history.append({
            "date_iso": d,
            "date_formatted": fmt_date,
            "pv_kwh": pv_k,
            "grid_kwh": gr_k,
            "total_kwh": round(tot_k, 2),
            "autarky_percent": aut,
            "savings_eur": sav_eur,
            "charging_cost_eur": d_cost_eur,
            "effective_price_ct_kwh": d_effective_price_ct
        })

    return {
        "grid_price_ct": grid_price,
        "feedin_price_ct": feedin_price,
        "saving_per_kwh_eur": round(saving_per_kwh_eur, 4),
        "total_pv_kwh": round(total_pv, 2),
        "total_grid_kwh": round(total_grid, 2),
        "total_charged_kwh": round(total_charged, 2),
        "autarky_percent": autarky_pct,
        "total_savings_eur": total_savings_eur,
        "total_charging_cost_eur": total_charging_cost_eur,
        "effective_price_ct_kwh": effective_price_ct_kwh,
        "co2_saved_kg": co2_saved_kg,
        "start_date": start_fmt,
        "end_date": end_fmt,
        "period_str": period_str,
        "today_pv_kwh": today_pv,
        "today_grid_kwh": today_grid,
        "today_total_kwh": round(today_charged, 2),
        "today_autarky_percent": today_autarky,
        "today_savings_eur": today_savings_eur,
        "today_charging_cost_eur": today_charging_cost_eur,
        "today_effective_price_ct_kwh": today_effective_price_ct_kwh,
        "daily_history": daily_history
    }

# Live Runtime Status
system_status = {
    "solaredge": {
        "connected": False,
        "pv_power_w": 0,
        "load_power_w": 0,
        "grid_power_w": 0,
        "grid_status": "Unknown",
        "last_update": None,
        "raw": {}
    },
    "goe": {
        "connected": False,
        "car_state": 1,
        "car_state_text": "Nicht verbunden",
        "ampere": 6,
        "force_state": 0,
        "phase_mode": 0,
        "charging_power_w": 0,
        "total_kwh": 0,
        "allowed": False,
        "last_update": None,
        "raw": {}
    },
    "controller": {
        "active_mode": global_config.get("mode", "pv"),
        "target_ampere": 0,
        "target_force": 1,
        "target_phases": 0,
        "calculated_surplus_w": 0,
        "effective_available_w": 0,
        "status_message": "System startet...",
        "last_control_time": None
    },
    "vkw_tariff": {
        "current_price_ct": 0.0,
        "epex_price_ct": 0.0,
        "deduction_ct": 0.60,
        "current_slot": "--:--",
        "min_price_ct": 0.0,
        "max_price_ct": 0.0,
        "last_update": None,
        "prices": []
    },
    "history": []
}

# --- VKW Dynamic Feed-in Tariff Fetcher ---
def fetch_vkw_tariff_data():
    try:
        url = "https://api.awattar.at/v1/marketdata"
        req = urllib.request.Request(url, headers={'User-Agent': 'GoEPVSteuerung/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8')).get('data', [])
        
        vkw_deduction_ct = 0.60  # 0.60 ct/kWh VKW Abschlag
        result = []
        now_ms = int(time.time() * 1000)
        current_item = None
        
        prices_list = []
        for item in data:
            start_ms = item['start_timestamp']
            end_ms = item['end_timestamp']
            market_eur_mwh = float(item.get('marketprice', 0))
            epex_ct_kwh = market_eur_mwh / 10.0
            vkw_tariff_ct_kwh = round(epex_ct_kwh - vkw_deduction_ct, 3)
            
            start_dt = datetime.fromtimestamp(start_ms / 1000.0)
            end_dt = datetime.fromtimestamp(end_ms / 1000.0)
            
            entry = {
                "start": start_dt.strftime("%H:%M"),
                "end": end_dt.strftime("%H:%M"),
                "date": start_dt.strftime("%d.%m."),
                "timestamp": start_ms,
                "epex_ct_kwh": round(epex_ct_kwh, 3),
                "vkw_tariff_ct_kwh": vkw_tariff_ct_kwh
            }
            result.append(entry)
            prices_list.append(vkw_tariff_ct_kwh)
            
            if start_ms <= now_ms < end_ms:
                current_item = entry

        if not current_item and result:
            current_item = result[0]
            
        min_price = min(prices_list) if prices_list else 0
        max_price = max(prices_list) if prices_list else 0
        
        return {
            "success": True,
            "current_price_ct": current_item["vkw_tariff_ct_kwh"] if current_item else 0.0,
            "epex_price_ct": current_item["epex_ct_kwh"] if current_item else 0.0,
            "deduction_ct": vkw_deduction_ct,
            "current_slot": f"{current_item['start']} - {current_item['end']}" if current_item else "--:--",
            "min_price_ct": min_price,
            "max_price_ct": max_price,
            "last_update": datetime.now().strftime("%H:%M:%S"),
            "prices": result
        }
    except Exception as e:
        print(f"[VKW-Tariff] Fehler beim Abrufen der Börsenpreise: {e}")
        return {"success": False, "error": str(e)}

# --- SolarEdge API Fetcher ---
def fetch_solaredge_data(api_key, site_id):
    url = f"https://monitoringapi.solaredge.com/site/{site_id}/currentPowerFlow?api_key={api_key}"
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={'User-Agent': 'GoEPVSteuerung/1.0'})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                flow = data.get("siteCurrentPowerFlow", {})
                
                pv_w = float(flow.get("PV", {}).get("currentPower", 0)) * 1000.0
                load_w = float(flow.get("LOAD", {}).get("currentPower", 0)) * 1000.0
                grid_w = float(flow.get("GRID", {}).get("currentPower", 0)) * 1000.0
                
                connections = flow.get("connections", [])
                grid_is_export = False
                grid_is_import = False
                for conn in connections:
                    frm = conn.get("from", "").upper()
                    to = conn.get("to", "").upper()
                    if frm in ["PV", "LOAD"] and to == "GRID":
                        grid_is_export = True
                    elif frm == "GRID" and to in ["LOAD", "PV"]:
                        grid_is_import = True

                if grid_is_import:
                    signed_grid_w = -abs(grid_w)
                elif grid_is_export:
                    signed_grid_w = abs(grid_w)
                else:
                    signed_grid_w = pv_w - load_w

                return {
                    "success": True,
                    "pv_power_w": round(pv_w, 1),
                    "load_power_w": round(load_w, 1),
                    "grid_power_w": round(signed_grid_w, 1),
                    "raw": flow
                }
            else:
                return {"success": False, "error": f"HTTP {resp.status}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- Go-e Charger Local HTTP API v2 / v1 Fetcher & Controller ---
def fetch_goe_status(ip):
    if not ip or ip.strip() == "":
        return {"success": False, "error": "Keine IP angegeben"}
    
    clean_ip = ip.strip().replace("http://", "").replace("https://", "").rstrip("/")
    
    url_v2 = f"http://{clean_ip}/api/status?filter=car,amp,frc,psm,nrg,alw,pha,wh"
    try:
        req = urllib.request.Request(url_v2, headers={'User-Agent': 'GoEPVSteuerung/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                
                car = data.get("car", 1)
                car_texts = {1: "Bereit / Kein Auto", 2: "Lädt", 3: "Wartet auf Auto", 4: "Ladevorgang beendet"}
                
                nrg = data.get("nrg", [])
                charging_w = 0
                if len(nrg) > 11:
                    charging_w = float(nrg[11])
                elif len(nrg) >= 3:
                    charging_w = float(sum(nrg[6:9])) if len(nrg) >= 9 else 0
                    
                total_wh = float(data.get("wh", 0))
                
                return {
                    "success": True,
                    "api_version": "v2",
                    "car_state": car,
                    "car_state_text": car_texts.get(car, f"Status {car}"),
                    "ampere": data.get("amp", 6),
                    "force_state": data.get("frc", 0),
                    "phase_mode": data.get("psm", 0),
                    "allowed": data.get("alw", False),
                    "charging_power_w": round(charging_w, 1),
                    "total_kwh": round(total_wh / 1000.0, 2),
                    "raw": data
                }
    except Exception as e_v2:
        url_v1 = f"http://{clean_ip}/status"
        try:
            req = urllib.request.Request(url_v1, headers={'User-Agent': 'GoEPVSteuerung/1.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    car = int(data.get("car", 1))
                    car_texts = {1: "Bereit / Kein Auto", 2: "Lädt", 3: "Wartet auf Auto", 4: "Ladevorgang beendet"}
                    
                    nrg = data.get("nrg", [])
                    charging_w = float(nrg[11]) if len(nrg) > 11 else 0
                    eto = float(data.get("eto", 0)) / 10.0
                    
                    return {
                        "success": True,
                        "api_version": "v1",
                        "car_state": car,
                        "car_state_text": car_texts.get(car, f"Status {car}"),
                        "ampere": int(data.get("amp", 6)),
                        "force_state": int(data.get("frc", 0)),
                        "phase_mode": int(data.get("psm", 0)),
                        "allowed": bool(data.get("alw", False)),
                        "charging_power_w": round(charging_w, 1),
                        "total_kwh": round(eto, 2),
                        "raw": data
                    }
        except Exception as e_v1:
            return {"success": False, "error": f"v2 failure ({e_v2}), v1 failure ({e_v1})"}

def set_goe_param(ip, params):
    if not ip or ip.strip() == "":
        return {"success": False, "error": "Keine IP angegeben"}
    
    clean_ip = ip.strip().replace("http://", "").replace("https://", "").rstrip("/")
    query_str = urllib.parse.urlencode(params)
    
    url_v2 = f"http://{clean_ip}/api/set?{query_str}"
    try:
        req = urllib.request.Request(url_v2, headers={'User-Agent': 'GoEPVSteuerung/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                return {"success": True, "api_version": "v2", "result": data}
    except Exception as e_v2:
        url_v1 = f"http://{clean_ip}/mqt?payload={query_str}"
        try:
            req = urllib.request.Request(url_v1, headers={'User-Agent': 'GoEPVSteuerung/1.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return {"success": True, "api_version": "v1"}
        except Exception as e_v1:
            return {"success": False, "error": f"v2 error: {e_v2}, v1 error: {e_v1}"}

def wakeup_goe_car(ip):
    """Triggers CP pulse (1 -> 0 -> 2 sequence) to wake up sleeping EV without manual car key/app intervention."""
    if not ip or ip.strip() == "":
        return {"success": False, "error": "Keine IP angegeben"}
    print(f"[Go-e] Sende 3-Stufen CP-Aufweckimpuls (frc=1 -> frc=0 -> frc=2) an {ip}...")
    res1 = set_goe_param(ip, {"frc": 1})
    time.sleep(4)
    res2 = set_goe_param(ip, {"frc": 0})
    time.sleep(4)
    res3 = set_goe_param(ip, {"frc": 2})  # Force ON (Aktiviert das Schütz im Fahrzeug)
    return {"success": True, "res_stop": res1, "res_neutral": res2, "res_start": res3}

# --- Background Controller Loop ---
def run_pv_controller():
    print("[PV-Controller] gestartet.")
    last_solaredge_fetch = 0
    last_vkw_fetch = 0
    last_reset_day = datetime.now().date()
    last_auto_wakeup_time = 0
    car_sleep_count = 0
    
    last_charging_start_time = 0
    last_charging_stop_time = 0
    off_delay_start_time = 0
    phase_switch_start_time = 0
    target_psm_candidate = 0
    is_charging_session_active = False
    
    pv_history = []
    load_history = []
    
    while True:
        try:
            now_dt = datetime.now()
            today = now_dt.date()
            if today != last_reset_day:
                last_reset_day = today
                with config_lock:
                    if global_config.get("midnight_reset", True):
                        reset_changes = []
                        if global_config.get("mode") == "normal":
                            global_config["mode"] = "pv"
                            reset_changes.append("Lademodus -> PV Laden")
                        if global_config.get("pv_threshold_watt", 0) != 0:
                            global_config["pv_threshold_watt"] = 0
                            reset_changes.append("Threshold -> 0 kW")
                        
                        if reset_changes:
                            save_config(global_config)
                            changes_str = ", ".join(reset_changes)
                            print(f"[{now_dt.strftime('%Y-%m-%d %H:%M:%S')}] [PV-Controller] Mitternachts-Reset durchgeführt ({changes_str}).")

            now = time.time()
            with config_lock:
                cfg = dict(global_config)
            
            poll_interval = int(cfg.get("solaredge_poll_seconds", 180))
            api_key = cfg.get("solaredge_api_key", "").strip()
            site_id = cfg.get("solaredge_site_id", "").strip()
            goe_ip = cfg.get("goe_ip", "").strip()
            mode = cfg.get("mode", "pv")
            pv_threshold = float(cfg.get("pv_threshold_watt", 0))
            normal_amp = int(cfg.get("normal_ampere", 16))
            min_pv_amp = int(cfg.get("min_pv_ampere", 6))
            max_pv_amp = int(cfg.get("max_pv_ampere", 16))
            phases_setting = cfg.get("phases_setting", "auto")
            
            off_delay_sec = int(cfg.get("off_delay_seconds", 180))
            min_pause_sec = int(cfg.get("min_pause_seconds", 120))
            enable_smoothing = cfg.get("enable_smoothing", True)

            if now - last_solaredge_fetch >= poll_interval:
                print(f"[PV-Controller] Hole SolarEdge Daten (Site {site_id})...")
                se_res = fetch_solaredge_data(api_key, site_id)
                with state_lock:
                    if se_res["success"]:
                        system_status["solaredge"]["connected"] = True
                        system_status["solaredge"]["pv_power_w"] = se_res["pv_power_w"]
                        system_status["solaredge"]["load_power_w"] = se_res["load_power_w"]
                        system_status["solaredge"]["grid_power_w"] = se_res["grid_power_w"]
                        system_status["solaredge"]["last_update"] = datetime.now().strftime("%H:%M:%S")
                        system_status["solaredge"]["raw"] = se_res["raw"]
                    else:
                        system_status["solaredge"]["connected"] = False
                last_solaredge_fetch = now

            if now - last_vkw_fetch >= 900 or last_vkw_fetch == 0: # Every 15 minutes
                print("[PV-Controller] Hole VKW Einspeisetarif & Börsenpreise...")
                vkw_res = fetch_vkw_tariff_data()
                with state_lock:
                    if vkw_res["success"]:
                        system_status["vkw_tariff"] = vkw_res
                        with savings_lock:
                            global_savings["feedin_price_ct"] = round(vkw_res["current_price_ct"], 2)
                            save_savings(global_savings)
                last_vkw_fetch = now

            goe_res = fetch_goe_status(goe_ip)
            with state_lock:
                if goe_res["success"]:
                    system_status["goe"]["connected"] = True
                    system_status["goe"]["car_state"] = goe_res["car_state"]
                    system_status["goe"]["car_state_text"] = goe_res["car_state_text"]
                    system_status["goe"]["ampere"] = goe_res["ampere"]
                    system_status["goe"]["force_state"] = goe_res["force_state"]
                    system_status["goe"]["phase_mode"] = goe_res["phase_mode"]
                    system_status["goe"]["allowed"] = goe_res["allowed"]
                    system_status["goe"]["charging_power_w"] = goe_res["charging_power_w"]
                    system_status["goe"]["total_kwh"] = goe_res["total_kwh"]
                    system_status["goe"]["last_update"] = datetime.now().strftime("%H:%M:%S")
                    system_status["goe"]["raw"] = goe_res["raw"]
                else:
                    system_status["goe"]["connected"] = False
                    system_status["goe"]["car_state_text"] = "Wallbox nicht erreichbar"

            pv_w = system_status["solaredge"]["pv_power_w"]
            load_w = system_status["solaredge"]["load_power_w"]
            grid_w = system_status["solaredge"]["grid_power_w"]
            goe_w = system_status["goe"]["charging_power_w"]

            if enable_smoothing:
                pv_history.append(pv_w)
                load_history.append(load_w)
                if len(pv_history) > 4:
                    pv_history.pop(0)
                if len(load_history) > 4:
                    load_history.pop(0)
                smoothed_pv_w = sum(pv_history) / len(pv_history)
                smoothed_load_w = sum(load_history) / len(load_history)
            else:
                smoothed_pv_w = pv_w
                smoothed_load_w = load_w

            house_base_w = max(0.0, smoothed_load_w - goe_w)
            raw_pv_surplus_w = smoothed_pv_w - house_base_w
            pv_surplus_w = max(0.0, raw_pv_surplus_w)
            available_w = max(pv_surplus_w, pv_threshold)

            # Energy accumulation for PV-savings statistics
            if 'last_loop_time' in locals():
                delta_sec = now - last_loop_time
                if goe_w > 0 and 0 < delta_sec < 120:
                    energy_kwh = (goe_w * delta_sec) / 3600000.0
                    pv_power_w = min(goe_w, pv_surplus_w)
                    pv_ratio = max(0.0, min(1.0, pv_power_w / goe_w)) if goe_w > 0 else 0.0
                    
                    pv_kwh = energy_kwh * pv_ratio
                    grid_kwh = energy_kwh * (1.0 - pv_ratio)
                    
                    today_str = now_dt.strftime("%Y-%m-%d")
                    with savings_lock:
                        global_savings["total_pv_kwh"] = global_savings.get("total_pv_kwh", 0.0) + pv_kwh
                        global_savings["total_grid_kwh"] = global_savings.get("total_grid_kwh", 0.0) + grid_kwh
                        
                        if "daily" not in global_savings:
                            global_savings["daily"] = {}
                        if today_str not in global_savings["daily"]:
                            global_savings["daily"][today_str] = {"pv_kwh": 0.0, "grid_kwh": 0.0}
                        
                        global_savings["daily"][today_str]["pv_kwh"] = global_savings["daily"][today_str].get("pv_kwh", 0.0) + pv_kwh
                        global_savings["daily"][today_str]["grid_kwh"] = global_savings["daily"][today_str].get("grid_kwh", 0.0) + grid_kwh
                        save_savings(global_savings)
            last_loop_time = now

            curr_psm = system_status["goe"].get("phase_mode", 0)
            if phases_setting == "1":
                target_psm = 1
                w_per_amp = 230.0
                min_power = min_pv_amp * 230.0
            elif phases_setting == "3":
                target_psm = 2
                w_per_amp = 690.0
                min_power = min_pv_amp * 690.0
            else:
                # Auto mode with hysteresis to prevent rapid 1-phase <-> 3-phase toggling at 4140W
                desired_psm = 2 if available_w >= 4140.0 else 1
                if curr_psm == 2 and available_w >= 3600.0:
                    desired_psm = 2
                
                if desired_psm != target_psm_candidate:
                    target_psm_candidate = desired_psm
                    phase_switch_start_time = now
                
                active_psm = curr_psm if curr_psm in [1, 2] else 1
                if target_psm_candidate != active_psm:
                    if now - phase_switch_start_time >= 60:
                        target_psm = target_psm_candidate
                    else:
                        target_psm = active_psm
                else:
                    target_psm = target_psm_candidate

                if target_psm == 2:
                    w_per_amp = 690.0
                    min_power = min_pv_amp * 690.0
                else:
                    w_per_amp = 230.0
                    min_power = min_pv_amp * 230.0

            target_amp = min_pv_amp
            target_frc = 0
            msg = ""

            min_run_time_sec = 300 # 5 minutes minimum runtime

            # Check manual pause_until schedule
            pause_until_str = cfg.get("pause_until", "")
            is_paused_by_user = False
            pause_until_dt = None
            if pause_until_str:
                try:
                    pause_until_dt = datetime.fromisoformat(pause_until_str)
                    if now_dt < pause_until_dt:
                        is_paused_by_user = True
                    else:
                        with config_lock:
                            global_config["pause_until"] = ""
                            save_config(global_config)
                        print(f"[{now_dt.strftime('%Y-%m-%d %H:%M:%S')}] [PV-Controller] Manuelle Ladepause abgelaufen ({pause_until_str}) - Laden wieder freigegeben.")
                        pause_until_str = ""
                except Exception as e:
                    print(f"[PV-Controller] Fehler beim Parsen von pause_until ({pause_until_str}): {e}")

            if is_paused_by_user and pause_until_dt:
                target_amp = min_pv_amp
                target_frc = 1  # Force Off / Paused
                remaining_sec = int((pause_until_dt - now_dt).total_seconds())
                rem_hours = remaining_sec // 3600
                rem_mins = (remaining_sec % 3600) // 60
                rem_str = f"{rem_hours} Std. {rem_mins} Min." if rem_hours > 0 else f"{rem_mins} Min."
                msg = f"⏸️ Laden manuell pausiert bis {pause_until_dt.strftime('%d.%m.%Y um %H:%M')} Uhr (noch {rem_str})"
            elif mode == "normal":
                target_frc = 2  # Force On
                target_amp = normal_amp
                if phases_setting in ["auto", "3"]:
                    target_psm = 2  # Im Normalmodus (11 kW) voll 3-phasig laden
                off_delay_start_time = 0
                is_charging_session_active = True
                msg = f"Normalmodus: Laden mit festen {normal_amp} A ({'3-phasig' if target_psm==2 else '1-phasig'}) aktiv"
            else:
                # Stock / Börsen or Standard PV
                is_boerse_override = False
                boerse_msg = ""
                
                if mode == "pv_boerse":
                    weekday = now_dt.weekday()
                    hour = now_dt.hour
                    in_schedule = (7 <= hour < 17) if weekday in [0, 1, 2, 3] else ((7 <= hour < 14) if weekday == 4 else True)
                    curr_tariff_ct = system_status["vkw_tariff"].get("current_price_ct", 0.0)
                    prices = [p["vkw_tariff_ct_kwh"] for p in system_status["vkw_tariff"].get("prices", [])]
                    avg_tariff_ct = (sum(prices) / len(prices)) if prices else curr_tariff_ct

                    if in_schedule:
                        if curr_tariff_ct < 0:
                            is_boerse_override = True
                            target_frc = 2
                            target_amp = max_pv_amp
                            boerse_msg = f"Börsenoptimiert: Negativer Tarif ({curr_tariff_ct:.2f} ct) → Max. Laden ({target_amp} A)"
                        elif curr_tariff_ct > avg_tariff_ct:
                            is_boerse_override = True
                            target_frc = 2 if available_w >= min_power else 1
                            target_amp = min_pv_amp
                            boerse_msg = f"Börsenoptimiert: Hoher Verkaufspreis ({curr_tariff_ct:.2f} ct/kWh > Schnitt {avg_tariff_ct:.2f} ct) → Ladestrom gedrosselt ({target_amp} A)"

                if is_boerse_override:
                    msg = boerse_msg
                else:
                    # Standard PV logic with Off-Delay & Min-Pause & Min-Runtime
                    if available_w < min_power:
                        if is_charging_session_active:
                            elapsed_charging = now - last_charging_start_time
                            if elapsed_charging < min_run_time_sec:
                                remaining_run = int(min_run_time_sec - elapsed_charging)
                                target_frc = 2
                                target_amp = min_pv_amp
                                msg = f"PV Laden gepuffert (⏱️ 5-Min. Mindestlaufzeit: noch {remaining_run}s). Verfügbar: {int(available_w)} W"
                            else:
                                if off_delay_start_time == 0:
                                    off_delay_start_time = now
                                elapsed_off = now - off_delay_start_time
                                if elapsed_off < off_delay_sec:
                                    remaining_off = int(off_delay_sec - elapsed_off)
                                    target_frc = 2
                                    target_amp = min_pv_amp
                                    msg = f"PV Laden gepuffert (⏳ Ausschaltverzögerung: noch {remaining_off}s bis Stopp). Verfügbar: {int(available_w)} W < {int(min_power)} W"
                                else:
                                    target_frc = 1
                                    target_amp = min_pv_amp
                                    is_charging_session_active = False
                                    last_charging_stop_time = now
                                    off_delay_start_time = 0
                                    msg = f"PV Laden pausiert: Verfügbar {int(available_w)} W < Benötigt {int(min_power)} W (Überschuss: {int(pv_surplus_w)} W, Netz-Toleranz: {round(pv_threshold/1000.0, 1)} kW)"
                        else:
                            target_frc = 1
                            target_amp = min_pv_amp
                            off_delay_start_time = 0
                            msg = f"PV Laden pausiert: Verfügbar {int(available_w)} W < Benötigt {int(min_power)} W (Überschuss: {int(pv_surplus_w)} W, Netz-Toleranz: {round(pv_threshold/1000.0, 1)} kW)"
                    else:
                        # available_w >= min_power
                        off_delay_start_time = 0
                        if not is_charging_session_active:
                            pause_elapsed = now - last_charging_stop_time
                            if last_charging_stop_time > 0 and pause_elapsed < min_pause_sec:
                                remaining_pause = int(min_pause_sec - pause_elapsed)
                                target_frc = 1
                                target_amp = min_pv_amp
                                msg = f"PV Laden pausiert (⏸️ Mindestpausenzeit: noch {remaining_pause}s bis Freigabe). Verfügbar: {int(available_w)} W"
                            else:
                                target_frc = 2
                                is_charging_session_active = True
                                last_charging_start_time = now
                                calculated_amp = int(available_w / w_per_amp)
                                target_amp = max(min_pv_amp, min(max_pv_amp, calculated_amp))
                                msg = f"PV Laden aktiv: {target_amp} A ({'3-phasig' if target_psm==2 else '1-phasig'}). Verfügbar: {int(available_w)} W"
                        else:
                            target_frc = 2
                            calculated_amp = int(available_w / w_per_amp)
                            target_amp = max(min_pv_amp, min(max_pv_amp, calculated_amp))
                            msg = f"PV Laden aktiv: {target_amp} A ({'3-phasig' if target_psm==2 else '1-phasig'}). Verfügbar: {int(available_w)} W"

            if goe_ip and system_status["goe"]["connected"]:
                curr_amp = system_status["goe"]["ampere"]
                curr_frc = system_status["goe"]["force_state"]
                curr_psm = system_status["goe"]["phase_mode"]

                params_to_set = {}
                if curr_amp != target_amp:
                    params_to_set["amp"] = target_amp
                if curr_frc != target_frc:
                    params_to_set["frc"] = target_frc
                if target_psm > 0 and curr_psm != target_psm:
                    params_to_set["psm"] = target_psm

                if params_to_set:
                    print(f"[PV-Controller] Sende neue Einstellungen an Go-e ({goe_ip}): {params_to_set}")
                    set_res = set_goe_param(goe_ip, params_to_set)
                    if not set_res["success"]:
                        msg += f" (Fehler beim Senden: {set_res.get('error')})"

                # Auto-Wakeup check for sleeping vehicle (State 3/4 with 0W while charge is desired)
                if cfg.get("auto_wakeup", True):
                    car_st = system_status["goe"]["car_state"]
                    chg_w = system_status["goe"]["charging_power_w"]
                    if target_frc in [0, 2] and available_w >= min_power and car_st in [3, 4] and chg_w == 0:
                        car_sleep_count += 1
                        if car_sleep_count >= 2 and (now - last_auto_wakeup_time) > 600:
                            print(f"[PV-Controller] Auto-Aufwecken ausgelöst für schlafendes Auto (State {car_st})...")
                            msg += " ⚡ (Auto schläft - CP-Aufweckimpuls gesendet)"
                            wakeup_goe_car(goe_ip)
                            last_auto_wakeup_time = now
                            car_sleep_count = 0
                    else:
                        car_sleep_count = 0

            with state_lock:
                system_status["controller"]["active_mode"] = mode
                system_status["controller"]["target_ampere"] = target_amp
                system_status["controller"]["target_force"] = target_frc
                system_status["controller"]["target_phases"] = target_psm
                system_status["controller"]["calculated_surplus_w"] = round(raw_pv_surplus_w, 1)
                system_status["controller"]["effective_available_w"] = round(available_w, 1)
                system_status["controller"]["status_message"] = msg
                system_status["controller"]["last_control_time"] = datetime.now().strftime("%H:%M:%S")

                hist_item = {
                    "time": datetime.now().strftime("%H:%M"),
                    "pv": round(pv_w, 1),
                    "load": round(load_w, 1),
                    "grid": round(grid_w, 1),
                    "charging": round(goe_w, 1),
                    "surplus": round(raw_pv_surplus_w, 1)
                }
                system_status["history"].append(hist_item)
                if len(system_status["history"]) > 60:
                    system_status["history"].pop(0)

        except Exception as e:
            print(f"[PV-Controller] Exception im Regelkreis: {e}")
            
        time.sleep(15)

# --- HTTP / HTTPS API & Static File Server Handler ---
class AppRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            with state_lock:
                with config_lock:
                    st = dict(system_status)
                    st["config"] = dict(global_config)
            st["savings"] = get_savings_summary()
            self.send_json_response(st)

        elif path == "/api/savings":
            self.send_json_response(get_savings_summary())

        elif path == "/api/test_goe":
            params = urllib.parse.parse_qs(parsed.query)
            ip = params.get("ip", [""])[0]
            res = fetch_goe_status(ip)
            self.send_json_response(res)

        elif path == "/api/wakeup_car":
            with config_lock:
                goe_ip = global_config.get("goe_ip", "")
            res = wakeup_goe_car(goe_ip)
            self.send_json_response(res)

        elif path == "/api/vkw_tariff":
            res = fetch_vkw_tariff_data()
            self.send_json_response(res)

        else:
            if path == "/":
                self.path = "/index.html"
            return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get('Content-Length', 0))
        post_body = self.rfile.read(content_len).decode('utf-8')
        
        try:
            data = json.loads(post_body) if post_body else {}
        except Exception:
            data = {}

        if path == "/api/config":
            with config_lock:
                for k in ["goe_ip", "mode", "pv_threshold_watt", "normal_ampere", "min_pv_ampere", "max_pv_ampere", "solaredge_poll_seconds", "phases_setting", "midnight_reset", "auto_wakeup", "off_delay_seconds", "min_pause_seconds", "enable_smoothing", "pause_until"]:
                    if k in data:
                        global_config[k] = data[k]
                save_config(global_config)
            self.send_json_response({"success": True, "config": global_config})

        elif path == "/api/pause_until":
            pause_val = data.get("pause_until", "")
            with config_lock:
                global_config["pause_until"] = pause_val if pause_val else ""
                save_config(global_config)
            self.send_json_response({"success": True, "pause_until": global_config["pause_until"], "config": global_config})

        elif path == "/api/savings/config":
            with savings_lock:
                if "grid_price_ct" in data:
                    global_savings["grid_price_ct"] = float(data["grid_price_ct"])
                if "feedin_price_ct" in data:
                    global_savings["feedin_price_ct"] = float(data["feedin_price_ct"])
                if data.get("reset") is True:
                    global_savings["total_pv_kwh"] = 0.0
                    global_savings["total_grid_kwh"] = 0.0
                    global_savings["daily"] = {}
                    global_savings["start_date"] = datetime.now().strftime("%Y-%m-%d")
                save_savings(global_savings)
            self.send_json_response({"success": True, "savings": get_savings_summary()})

        elif path == "/api/wakeup_car":
            with config_lock:
                goe_ip = global_config.get("goe_ip", "")
            res = wakeup_goe_car(goe_ip)
            self.send_json_response(res)

        elif path == "/api/force_poll":
            with config_lock:
                api_key = global_config["solaredge_api_key"]
                site_id = global_config["solaredge_site_id"]
                goe_ip = global_config["goe_ip"]
            
            se_res = fetch_solaredge_data(api_key, site_id)
            goe_res = fetch_goe_status(goe_ip)

            with state_lock:
                if se_res["success"]:
                    system_status["solaredge"]["connected"] = True
                    system_status["solaredge"]["pv_power_w"] = se_res["pv_power_w"]
                    system_status["solaredge"]["load_power_w"] = se_res["load_power_w"]
                    system_status["solaredge"]["grid_power_w"] = se_res["grid_power_w"]
                    system_status["solaredge"]["last_update"] = datetime.now().strftime("%H:%M:%S")
                if goe_res["success"]:
                    system_status["goe"]["connected"] = True
                    system_status["goe"]["car_state"] = goe_res["car_state"]
                    system_status["goe"]["car_state_text"] = goe_res["car_state_text"]
                    system_status["goe"]["ampere"] = goe_res["ampere"]
                    system_status["goe"]["force_state"] = goe_res["force_state"]
                    system_status["goe"]["charging_power_w"] = goe_res["charging_power_w"]
                    system_status["goe"]["total_kwh"] = goe_res["total_kwh"]
                    system_status["goe"]["last_update"] = datetime.now().strftime("%H:%M:%S")

            self.send_json_response({"success": True})
        else:
            self.send_error(404, "Endpoint not found")

    def send_json_response(self, obj):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def main():
    port = global_config.get("server_port", 8080)
    
    t = threading.Thread(target=run_pv_controller, daemon=True)
    t.start()
    
    web_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(web_dir)
    
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), AppRequestHandler) as httpd:
        if os.path.exists(SERVER_CRT) and os.path.exists(SERVER_KEY):
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_ctx.load_cert_chain(certfile=SERVER_CRT, keyfile=SERVER_KEY)
            httpd.socket = ssl_ctx.wrap_socket(httpd.socket, server_side=True)
            print(f"==================================================")
            print(f"   Go-e & SolarEdge PV Steuerungs-Server gestartet!")
            print(f"   HTTPS Website erreichbar unter: https://localhost:{port}")
            print(f"==================================================")
        else:
            print(f"==================================================")
            print(f"   Go-e & SolarEdge PV Steuerungs-Server gestartet!")
            print(f"   HTTP Website erreichbar unter: http://localhost:{port}")
            print(f"==================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer wird beendet.")

if __name__ == "__main__":
    main()
