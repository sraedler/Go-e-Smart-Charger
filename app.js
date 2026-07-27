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
            if (data.vkw_tariff) {
                updateVkwTariffUI(data.vkw_tariff, data.solaredge ? data.solaredge.grid_power_w : 0);
            }
            
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
    let modeText = "PV-Laden";
    if (mode === "normal") modeText = "Normal Laden";
    else if (mode === "pv_boerse") modeText = "PV Börsenoptimiert";

    document.getElementById("current-mode-label").innerText = modeText;
    
    const mobileStickyMode = document.getElementById("mobile-sticky-mode");
    if (mobileStickyMode) mobileStickyMode.innerText = modeText;
    
    const btnNormal = document.getElementById("btn-mode-normal");
    const btnPv = document.getElementById("btn-mode-pv");
    const btnPvBoerse = document.getElementById("btn-mode-pv-boerse");
    const pvBox = document.getElementById("pv-threshold-box");
    const normalBox = document.getElementById("normal-setting-box");
    const boerseBanner = document.getElementById("boerse-schedule-banner");

    btnNormal.classList.remove("active");
    btnPv.classList.remove("active");
    if (btnPvBoerse) btnPvBoerse.classList.remove("active");

    if (mode === "pv_boerse") {
        if (btnPvBoerse) btnPvBoerse.classList.add("active");
        pvBox.style.display = "block";
        normalBox.style.display = "none";
        if (boerseBanner) boerseBanner.style.display = "flex";
    } else if (mode === "pv") {
        btnPv.classList.add("active");
        pvBox.style.display = "block";
        normalBox.style.display = "none";
        if (boerseBanner) boerseBanner.style.display = "none";
    } else {
        btnNormal.classList.add("active");
        pvBox.style.display = "none";
        normalBox.style.display = "block";
        if (boerseBanner) boerseBanner.style.display = "none";
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

// Update VKW Dynamic Feed-in Tariff & Chart UI
let tariffChartInstance = null;

function updateVkwTariffUI(vkw, gridW) {
    if (!vkw) return;

    const currPrice = parseFloat(vkw.current_price_ct || 0);
    const epexPrice = parseFloat(vkw.epex_price_ct || 0);
    const deduction = parseFloat(vkw.deduction_ct || 0.60);

    const priceEl = document.getElementById("val-vkw-current-price");
    if (priceEl) {
        priceEl.innerText = currPrice.toFixed(2);
        priceEl.style.color = currPrice < 0 ? "#ff1744" : "#00e676";
    }

    const formulaEl = document.getElementById("val-vkw-formula");
    if (formulaEl) {
        formulaEl.innerText = `EPEX: ${epexPrice.toFixed(2)} ct/kWh − ${deduction.toFixed(2)} ct VKW-Abschlag (Netto)`;
    }

    const exportKw = gridW > 0 ? (gridW / 1000.0) : 0;
    const earningEurH = exportKw * (currPrice / 100.0);
    const earningEl = document.getElementById("val-vkw-current-earning");
    const earningSub = document.getElementById("val-vkw-earning-subtext");

    if (earningEl) {
        earningEl.innerText = `${earningEurH >= 0 ? '+' : ''}${earningEurH.toFixed(2)} €/h`;
        earningEl.style.color = earningEurH < 0 ? "#ff1744" : "#00e676";
    }
    if (earningSub) {
        earningSub.innerText = `bei ${exportKw.toFixed(2)} kW Netzeinspeisung`;
    }

    const maxEl = document.getElementById("val-vkw-max-price");
    const minEl = document.getElementById("val-vkw-min-price");
    const slotEl = document.getElementById("val-vkw-slot-time");

    if (maxEl) maxEl.innerText = `${(vkw.max_price_ct || 0).toFixed(2)} ct/kWh`;
    if (minEl) minEl.innerText = `${(vkw.min_price_ct || 0).toFixed(2)} ct/kWh`;
    if (slotEl) slotEl.innerText = vkw.current_slot || "--:--";

    if (vkw.prices && vkw.prices.length > 0) {
        renderTariffChart(vkw.prices);
    }
}

function renderTariffChart(prices) {
    if (!prices || prices.length === 0) return;

    const canvas = document.getElementById("tariffChart");
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    const labels = prices.map(p => p.start);
    const epexData = prices.map(p => p.epex_ct_kwh);
    const vkwData = prices.map(p => p.vkw_tariff_ct_kwh);

    if (tariffChartInstance) {
        tariffChartInstance.data.labels = labels;
        tariffChartInstance.data.datasets[0].data = epexData;
        tariffChartInstance.data.datasets[1].data = vkwData;
        tariffChartInstance.update();
        return;
    }

    if (typeof Chart === 'undefined') return;

    tariffChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'EPEX Spot AT (ct/kWh)',
                    data: epexData,
                    backgroundColor: 'rgba(41, 182, 246, 0.25)',
                    borderColor: '#29b6f6',
                    borderWidth: 1.5,
                    borderRadius: 4
                },
                {
                    label: 'VKW Auszahlung (ct/kWh)',
                    data: vkwData,
                    backgroundColor: prices.map(p => p.vkw_tariff_ct_kwh < 0 ? 'rgba(255, 23, 68, 0.7)' : 'rgba(0, 230, 118, 0.75)'),
                    borderColor: prices.map(p => p.vkw_tariff_ct_kwh < 0 ? '#ff1744' : '#00e676'),
                    borderWidth: 2,
                    borderRadius: 4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${context.raw.toFixed(2)} ct/kWh`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8', font: { family: 'Outfit', size: 10 } }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.08)' },
                    ticks: {
                        color: '#94a3b8',
                        font: { family: 'Outfit', size: 11 },
                        callback: function(val) { return val + ' ct'; }
                    }
                }
            }
        }
    });
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
