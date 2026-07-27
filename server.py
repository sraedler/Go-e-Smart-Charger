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
config_lock = threading.Lock()
state_lock = threading.Lock()

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
    "midnight_reset": True
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
    "history": []
}

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

# --- Background Controller Loop ---
def run_pv_controller():
    print("[PV-Controller] gestartet.")
    last_solaredge_fetch = 0
    last_reset_day = datetime.now().date()
    
    while True:
        try:
            now_dt = datetime.now()
            today = now_dt.date()
            if today != last_reset_day:
                last_reset_day = today
                with config_lock:
                    if global_config.get("midnight_reset", True):
                        reset_changes = []
                        if global_config.get("mode") != "pv":
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

            house_base_w = max(0.0, load_w - goe_w)
            pv_surplus_w = pv_w - house_base_w
            available_w = pv_surplus_w + pv_threshold

            target_amp = min_pv_amp
            target_frc = 0
            target_psm = 0
            msg = ""

            if mode == "normal":
                target_frc = 0
                target_amp = normal_amp
                msg = f"Normalmodus: Laden mit festen {normal_amp} A"
            else:
                if phases_setting == "1":
                    w_per_amp = 230.0
                    min_power = 6.0 * 230.0
                    target_psm = 1
                elif phases_setting == "3":
                    w_per_amp = 690.0
                    min_power = 6.0 * 690.0
                    target_psm = 2
                else:
                    if available_w >= 4140.0:
                        w_per_amp = 690.0
                        min_power = 4140.0
                        target_psm = 2
                    else:
                        w_per_amp = 230.0
                        min_power = 1380.0
                        target_psm = 1

                if available_w < min_power:
                    target_frc = 1
                    target_amp = min_pv_amp
                    msg = f"PV Laden pausiert: Verfügbar {int(available_w)} W < Benötigt {int(min_power)} W (Überschuss: {int(pv_surplus_w)} W, Netz-Toleranz: {round(pv_threshold/1000.0, 1)} kW)"
                else:
                    target_frc = 0
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

            with state_lock:
                system_status["controller"]["active_mode"] = mode
                system_status["controller"]["target_ampere"] = target_amp
                system_status["controller"]["target_force"] = target_frc
                system_status["controller"]["target_phases"] = target_psm
                system_status["controller"]["calculated_surplus_w"] = round(pv_surplus_w, 1)
                system_status["controller"]["effective_available_w"] = round(available_w, 1)
                system_status["controller"]["status_message"] = msg
                system_status["controller"]["last_control_time"] = datetime.now().strftime("%H:%M:%S")

                hist_item = {
                    "time": datetime.now().strftime("%H:%M"),
                    "pv": round(pv_w, 1),
                    "load": round(load_w, 1),
                    "grid": round(grid_w, 1),
                    "charging": round(goe_w, 1),
                    "surplus": round(pv_surplus_w, 1)
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
            self.send_json_response(st)

        elif path == "/api/test_goe":
            params = urllib.parse.parse_qs(parsed.query)
            ip = params.get("ip", [""])[0]
            res = fetch_goe_status(ip)
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
                for k in ["goe_ip", "mode", "pv_threshold_watt", "normal_ampere", "min_pv_ampere", "max_pv_ampere", "solaredge_poll_seconds", "phases_setting", "midnight_reset"]:
                    if k in data:
                        global_config[k] = data[k]
                save_config(global_config)
            self.send_json_response({"success": True, "config": global_config})

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
