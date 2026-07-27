// Global App State
let currentConfig = {
    goe_ip: "192.168.100.67",
    mode: "pv",
    pv_threshold_watt: 0,
    normal_ampere: 16,
    solaredge_poll_seconds: 180
};

// DOM Content Loaded
document.addEventListener("DOMContentLoaded", () => {
    fetchStatus();
    setInterval(fetchStatus, 3000); // Poll status every 3 seconds

    document.getElementById("btn-refresh").addEventListener("click", () => {
        const btn = document.getElementById("btn-refresh");
        btn.style.transform = "rotate(360deg)";
        fetch("/api/force_poll", { method: "POST" })
            .then(() => fetchStatus())
            .finally(() => setTimeout(() => btn.style.transform = "none", 500));
    });
});

// Fetch complete system status from backend
function fetchStatus() {
    fetch("/api/status")
        .then(res => res.json())
        .then(data => {
            if (data.config) {
                currentConfig = data.config;
                syncConfigUI(data.config);
            }
            updateSolarEdgeUI(data.solaredge);
            updateGoEUI(data.goe);
            updateControllerUI(data.controller);
            
            document.getElementById("system-status-text").innerText = "Aktiv & Synchronisiert";
            document.getElementById("system-status-badge").style.borderColor = "rgba(0, 230, 118, 0.4)";
        })
        .catch(err => {
            console.error("Fehler beim Abrufen des Status:", err);
            document.getElementById("system-status-text").innerText = "Verbindungsfehler";
            document.getElementById("system-status-badge").style.borderColor = "rgba(255, 23, 68, 0.4)";
        });
}

// Sync UI elements with current loaded config
function syncConfigUI(cfg) {
    // Mode UI
    const mode = cfg.mode || "pv";
    const modeText = mode === "pv" ? "PV-Laden" : "Normal Laden";
    document.getElementById("current-mode-label").innerText = modeText;
    
    const mobileStickyMode = document.getElementById("mobile-sticky-mode");
    if (mobileStickyMode) mobileStickyMode.innerText = modeText;
    
    const btnNormal = document.getElementById("btn-mode-normal");
    const btnPv = document.getElementById("btn-mode-pv");
    const pvBox = document.getElementById("pv-threshold-box");
    const normalBox = document.getElementById("normal-setting-box");

    if (mode === "pv") {
        btnPv.classList.add("active");
        btnNormal.classList.remove("active");
        pvBox.style.display = "block";
        normalBox.style.display = "none";
    } else {
        btnNormal.classList.add("active");
        btnPv.classList.remove("active");
        pvBox.style.display = "none";
        normalBox.style.display = "block";
    }

    // Threshold UI
    const thresh = cfg.pv_threshold_watt || 0;
    const slider = document.getElementById("threshold-slider");
    if (document.activeElement !== slider) {
        slider.value = thresh;
        updateThresholdDisplay(thresh);
    }

    // Go-e IP Input
    const ipInput = document.getElementById("goe-ip-input");
    if (document.activeElement !== ipInput && cfg.goe_ip) {
        ipInput.value = cfg.goe_ip;
    }

    // Auto Wakeup Checkbox
    const chkAutoWakeup = document.getElementById("chk-auto-wakeup");
    if (chkAutoWakeup) {
        chkAutoWakeup.checked = cfg.auto_wakeup !== false;
    }

    // Normal Ampere UI
    const normalAmp = cfg.normal_ampere || 16;
    document.querySelectorAll(".amp-btn").forEach(btn => {
        btn.classList.remove("active");
        if (btn.innerText.includes(`${normalAmp} A`)) {
            btn.classList.add("active");
        }
    });
}

// Update SolarEdge Solar & Power Flow UI
function updateSolarEdgeUI(se) {
    if (!se) return;
    
    const pvKw = (se.pv_power_w / 1000.0).toFixed(2);
    const loadKw = (se.load_power_w / 1000.0).toFixed(2);
    const gridW = se.grid_power_w || 0;
    const gridKw = (Math.abs(gridW) / 1000.0).toFixed(2);

    document.getElementById("val-pv-power").innerText = `${pvKw} kW`;
    document.getElementById("val-load-power").innerText = `${loadKw} kW`;
    
    const gridLabel = document.getElementById("label-grid");
    const gridVal = document.getElementById("val-grid-power");
    
    if (gridW >= 0) {
        gridLabel.innerText = "Netzeinspeisung";
        gridVal.innerText = `${gridKw} kW`;
        gridVal.style.color = "#00e676";
    } else {
        gridLabel.innerText = "Netzbezug";
        gridVal.innerText = `${gridKw} kW`;
        gridVal.style.color = "#ff9100";
    }

    if (se.last_update) {
        document.getElementById("solaredge-update-time").innerText = `Letztes Update: ${se.last_update}`;
    }
}

// Update Go-e Wallbox UI
function updateGoEUI(goe) {
    if (!goe) return;

    const carPowerKw = (goe.charging_power_w / 1000.0).toFixed(2);
    document.getElementById("val-car-power").innerText = `${carPowerKw} kW`;
    document.getElementById("val-goe-power").innerText = `${carPowerKw} kW`;

    document.getElementById("val-goe-amp").innerText = `${goe.ampere || '--'} A`;
    document.getElementById("val-goe-kwh").innerText = `${goe.total_kwh || '0.0'} kWh`;

    const phases = goe.phase_mode === 1 ? "1-phasig" : (goe.phase_mode === 2 ? "3-phasig" : "Auto");
    document.getElementById("val-goe-phases").innerText = phases;

    const stateTag = document.getElementById("wallbox-state-tag");
    stateTag.innerText = goe.car_state_text || "Unbekannt";
    
    if (goe.car_state === 2) {
        stateTag.style.background = "rgba(0, 230, 118, 0.2)";
        stateTag.style.color = "#00e676";
        stateTag.style.borderColor = "#00e676";
    } else {
        stateTag.style.background = "rgba(255, 255, 255, 0.08)";
        stateTag.style.color = "var(--text-main)";
        stateTag.style.borderColor = "var(--card-border)";
    }
}

// Update Controller UI & Status Banner
function updateControllerUI(ctrl) {
    if (!ctrl) return;

    const surplusRounded = Math.round(ctrl.calculated_surplus_w || 0);
    const availableRounded = Math.round(ctrl.effective_available_w || 0);

    document.getElementById("val-pv-surplus").innerText = `${surplusRounded} W`;
    document.getElementById("val-effective-available").innerText = `${availableRounded} W`;
    
    const mobileStickySurplus = document.getElementById("mobile-sticky-surplus");
    if (mobileStickySurplus) mobileStickySurplus.innerText = `${surplusRounded} W`;

    const bannerText = document.getElementById("controller-banner-text");
    if (ctrl.status_message) {
        bannerText.innerText = ctrl.status_message;
    }
}

// Actions
function setMode(newMode) {
    currentConfig.mode = newMode;
    saveConfigToServer({ mode: newMode });
}

function updateThresholdDisplay(val) {
    const numWatt = parseFloat(val) || 0;
    document.getElementById("threshold-val-num").innerText = (numWatt / 1000.0).toFixed(1);
}

function saveThreshold(val) {
    const num = parseInt(val, 10);
    currentConfig.pv_threshold_watt = num;
    saveConfigToServer({ pv_threshold_watt: num });
}

function setThresholdPreset(val) {
    document.getElementById("threshold-slider").value = val;
    updateThresholdDisplay(val);
    saveThreshold(val);
}

function setNormalAmpere(amp) {
    currentConfig.normal_ampere = amp;
    saveConfigToServer({ normal_ampere: amp });
}

function saveGoeIp() {
    const ip = document.getElementById("goe-ip-input").value.trim();
    saveConfigToServer({ goe_ip: ip });
    testGoeIp();
}

function testGoeIp() {
    const ip = document.getElementById("goe-ip-input").value.trim();
    const feedback = document.getElementById("ip-feedback-msg");
    if (!ip) {
        feedback.innerText = "Bitte gib eine IP-Adresse ein.";
        feedback.style.color = "#ff1744";
        return;
    }

    feedback.innerText = "Prüfe Verbindung...";
    feedback.style.color = "#29b6f6";

    fetch(`/api/test_goe?ip=${encodeURIComponent(ip)}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                feedback.innerText = `Erfolgreich verbunden (API ${data.api_version.toUpperCase()})! Wallbox Status: ${data.car_state_text}`;
                feedback.style.color = "#00e676";
                fetchStatus();
            } else {
                feedback.innerText = `Fehler: ${data.error || 'Wallbox nicht erreichbar'}. Prüfe die IP & erstelle Sicher, dass API v2 in der App aktiv ist.`;
                feedback.style.color = "#ff1744";
            }
        })
        .catch(err => {
            feedback.innerText = `Verbindungsfehler: ${err.message}`;
            feedback.style.color = "#ff1744";
        });
}

function toggleAutoWakeup(checked) {
    currentConfig.auto_wakeup = checked;
    saveConfigToServer({ auto_wakeup: checked });
}

function wakeupCar() {
    const btn = document.getElementById("btn-wakeup-car");
    if (!btn) return;

    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Aufwecksignal wird gesendet...`;

    fetch("/api/wakeup_car", { method: "POST" })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                btn.innerHTML = `<i class="fa-solid fa-check"></i> Aufweck-Impuls gesendet!`;
                setTimeout(() => fetchStatus(), 3500);
            } else {
                btn.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Fehler: ${data.error || 'Fehlgeschlagen'}`;
            }
        })
        .catch(err => {
            btn.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Verbindungsfehler`;
        })
        .finally(() => {
            setTimeout(() => {
                btn.disabled = false;
                btn.innerHTML = originalHtml;
            }, 5000);
        });
}

function saveConfigToServer(patch) {
    fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch)
    })
    .then(res => res.json())
    .then(data => {
        if (data.success && data.config) {
            syncConfigUI(data.config);
            fetchStatus();
        }
    })
    .catch(err => console.error("Fehler beim Speichern der Konfiguration:", err));
}
