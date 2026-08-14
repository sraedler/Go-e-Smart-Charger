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
            if (data.savings) {
                updateSavingsUI(data.savings);
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

    // Smoothing & Delay UI
    const selOffDelay = document.getElementById("select-off-delay");
    if (selOffDelay && document.activeElement !== selOffDelay) {
        selOffDelay.value = cfg.off_delay_seconds !== undefined ? cfg.off_delay_seconds : 180;
    }

    const selMinPause = document.getElementById("select-min-pause");
    if (selMinPause && document.activeElement !== selMinPause) {
        selMinPause.value = cfg.min_pause_seconds !== undefined ? cfg.min_pause_seconds : 120;
    }

    const chkSmoothing = document.getElementById("chk-enable-smoothing");
    if (chkSmoothing && document.activeElement !== chkSmoothing) {
        chkSmoothing.checked = cfg.enable_smoothing !== false;
    }

    // Handle pause_until status & banner
    const pauseBanner = document.getElementById("active-pause-banner");
    const pauseControls = document.getElementById("pause-controls");
    const inputPause = document.getElementById("input-pause-until");

    if (cfg.pause_until) {
        const pauseDt = new Date(cfg.pause_until);
        const nowDt = new Date();
        if (pauseDt > nowDt) {
            const pad = (n) => String(n).padStart(2, '0');
            const formattedUntil = `${pad(pauseDt.getDate())}.${pad(pauseDt.getMonth()+1)}.${pauseDt.getFullYear()} um ${pad(pauseDt.getHours())}:${pad(pauseDt.getMinutes())}`;
            
            const diffMs = pauseDt - nowDt;
            const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
            const diffMins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
            
            let remText = "";
            if (diffHours > 0) {
                remText = `noch ${diffHours} Std. ${diffMins} Min.`;
            } else {
                remText = `noch ${diffMins} Min.`;
            }

            const titleEl = document.getElementById("pause-banner-title");
            const countdownEl = document.getElementById("pause-banner-countdown");
            if (titleEl) titleEl.innerText = `Laden pausiert bis ${formattedUntil} Uhr`;
            if (countdownEl) countdownEl.innerText = remText;

            if (pauseBanner) pauseBanner.style.display = "flex";
            if (pauseControls) pauseControls.style.display = "none";
        } else {
            if (pauseBanner) pauseBanner.style.display = "none";
            if (pauseControls) pauseControls.style.display = "block";
        }
    } else {
        if (pauseBanner) pauseBanner.style.display = "none";
        if (pauseControls) pauseControls.style.display = "block";
    }

    if (inputPause && !cfg.pause_until && document.activeElement !== inputPause) {
        const defaultDt = new Date(Date.now() + 3600000);
        const pad = (n) => String(n).padStart(2, '0');
        inputPause.value = `${defaultDt.getFullYear()}-${pad(defaultDt.getMonth()+1)}-${pad(defaultDt.getDate())}T${pad(defaultDt.getHours())}:${pad(defaultDt.getMinutes())}`;
    }

    updatePausePresetsValidity();
}

// Smart Power Formatter (e.g. "350 W" vs "2.85 kW")
function formatPower(w) {
    if (w === undefined || w === null || isNaN(w)) return "0 W";
    const absW = Math.abs(w);
    if (absW >= 1000) {
        return `${(w / 1000.0).toFixed(2)} kW`;
    } else {
        return `${Math.round(w)} W`;
    }
}

// Update SolarEdge Solar & Power Flow UI
function updateSolarEdgeUI(se) {
    if (!se) return;
    
    const pvW = se.pv_power_w || 0;
    const loadW = se.load_power_w || 0;
    const gridW = se.grid_power_w || 0;

    const elPv = document.getElementById("val-pv-power");
    if (elPv) elPv.innerText = formatPower(pvW);

    const elLoad = document.getElementById("val-load-power");
    if (elLoad) elLoad.innerText = formatPower(loadW);
    
    const gridLabel = document.getElementById("label-grid");
    const gridVal = document.getElementById("val-grid-power");
    
    if (gridLabel && gridVal) {
        if (gridW >= 0) {
            gridLabel.innerText = "Netzeinspeisung";
            gridVal.innerText = formatPower(gridW);
            gridVal.style.color = "#00e676";
        } else {
            gridLabel.innerText = "Netzbezug";
            gridVal.innerText = formatPower(Math.abs(gridW));
            gridVal.style.color = "#ff9100";
        }
    }

    if (se.last_update) {
        const timeEl = document.getElementById("solaredge-update-time");
        if (timeEl) timeEl.innerText = `Letztes Update: ${se.last_update}`;
    }
}

// Update Go-e Wallbox UI
function updateGoEUI(goe) {
    if (!goe) return;

    const carPowerW = goe.charging_power_w || 0;
    const elCarPower = document.getElementById("val-car-power");
    if (elCarPower) elCarPower.innerText = formatPower(carPowerW);

    const elGoePower = document.getElementById("val-goe-power");
    if (elGoePower) elGoePower.innerText = formatPower(carPowerW);

    const elAmp = document.getElementById("val-goe-amp");
    if (elAmp) elAmp.innerText = `${goe.ampere || '--'} A`;

    const elKwh = document.getElementById("val-goe-kwh");
    if (elKwh) elKwh.innerText = `${goe.total_kwh || '0.0'} kWh`;

    const phases = goe.phase_mode === 1 ? "1-phasig" : (goe.phase_mode === 2 ? "3-phasig" : "Auto");
    const elPhases = document.getElementById("val-goe-phases");
    if (elPhases) elPhases.innerText = phases;

    const stateTag = document.getElementById("wallbox-state-tag");
    if (stateTag) {
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
}

// Update Controller UI & Status Banner
function updateControllerUI(ctrl) {
    if (!ctrl) return;

    const surplusW = ctrl.calculated_surplus_w || 0;
    const availableW = ctrl.effective_available_w || 0;

    const elSurplus = document.getElementById("val-pv-surplus");
    if (elSurplus) {
        elSurplus.innerText = formatPower(surplusW);
        if (surplusW < 0) {
            elSurplus.style.color = "#ff4d4d";
        } else if (surplusW > 0) {
            elSurplus.style.color = "#00e676";
        } else {
            elSurplus.style.color = "#ffffff";
        }
    }

    const elAvail = document.getElementById("val-effective-available");
    if (elAvail) elAvail.innerText = formatPower(availableW);
    
    const mobileStickySurplus = document.getElementById("mobile-sticky-surplus");
    if (mobileStickySurplus) {
        mobileStickySurplus.innerText = formatPower(surplusW);
        if (surplusW < 0) {
            mobileStickySurplus.style.color = "#ff4d4d";
        } else if (surplusW > 0) {
            mobileStickySurplus.style.color = "#00e676";
        } else {
            mobileStickySurplus.style.color = "#00e676";
        }
    }

    const bannerText = document.getElementById("controller-banner-text");
    if (bannerText && ctrl.status_message) {
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

function saveSmoothingConfig() {
    const offDelay = parseInt(document.getElementById("select-off-delay").value, 10);
    const minPause = parseInt(document.getElementById("select-min-pause").value, 10);
    const enableSmoothing = document.getElementById("chk-enable-smoothing").checked;

    saveConfigToServer({
        off_delay_seconds: offDelay,
        min_pause_seconds: minPause,
        enable_smoothing: enableSmoothing
    });
}

// Pause Until Functions
function submitPauseUntil() {
    const input = document.getElementById("input-pause-until");
    if (!input || !input.value) {
        alert("Bitte wählen Sie ein Datum und eine Uhrzeit aus.");
        return;
    }

    const dt = new Date(input.value);
    if (isNaN(dt.getTime())) {
        alert("Ungültiges Datum gewählt.");
        return;
    }

    if (dt <= new Date()) {
        alert("Der Zeitpunkt für die Pause muss in der Zukunft liegen.");
        return;
    }

    const pad = (n) => String(n).padStart(2, '0');
    const isoStr = `${dt.getFullYear()}-${pad(dt.getMonth()+1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;

    fetch("/api/pause_until", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pause_until: isoStr })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            fetchStatus();
        }
    })
    .catch(err => console.error("Fehler beim Setzen der Ladepause:", err));
}

function cancelPauseUntil() {
    fetch("/api/pause_until", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pause_until: "" })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            fetchStatus();
        }
    })
    .catch(err => console.error("Fehler beim Beenden der Ladepause:", err));
}

function setPausePresetTargetDay(daysAhead, targetHour) {
    const now = new Date();
    const target = new Date();
    target.setDate(now.getDate() + daysAhead);
    target.setHours(targetHour, 0, 0, 0);

    if (target <= now) {
        alert("Dieser Zeitpunkt liegt bereits in der Vergangenheit.");
        return;
    }

    const pad = (n) => String(n).padStart(2, '0');
    const val = `${target.getFullYear()}-${pad(target.getMonth()+1)}-${pad(target.getDate())}T${pad(targetHour)}:00`;
    
    const input = document.getElementById("input-pause-until");
    if (input) {
        input.value = val;
    }
}

function updatePausePresetsValidity() {
    const now = new Date();
    const checkPreset = (btnId, daysAhead, hour) => {
        const btn = document.getElementById(btnId);
        if (!btn) return;
        const target = new Date();
        target.setDate(now.getDate() + daysAhead);
        target.setHours(hour, 0, 0, 0);

        if (target <= now) {
            btn.classList.add("disabled");
        } else {
            btn.classList.remove("disabled");
        }
    };

    checkPreset("btn-preset-today-10", 0, 10);
    checkPreset("btn-preset-today-15", 0, 15);
    checkPreset("btn-preset-tomorrow-10", 1, 10);
    checkPreset("btn-preset-tomorrow-15", 1, 15);
}

// PV Charging Savings & Statistics UI
let savingsBarChartInstance = null;
let autarkyDonutChartInstance = null;

function updateSavingsUI(savings) {
    if (!savings) return;

    const totalEur = savings.total_savings_eur !== undefined ? savings.total_savings_eur.toFixed(2) : "0.00";
    const totalCost = savings.total_charging_cost_eur !== undefined ? savings.total_charging_cost_eur.toFixed(2) : "0.00";
    const effectivePrice = savings.effective_price_ct_kwh !== undefined ? savings.effective_price_ct_kwh.toFixed(1) : "0.0";
    const pvKwh = savings.total_pv_kwh !== undefined ? savings.total_pv_kwh.toFixed(1) : "0.0";
    const gridKwh = savings.total_grid_kwh !== undefined ? savings.total_grid_kwh.toFixed(1) : "0.0";
    const co2Kg = savings.co2_saved_kg !== undefined ? savings.co2_saved_kg.toFixed(1) : "0.0";
    const autarkyPct = savings.autarky_percent !== undefined ? savings.autarky_percent.toFixed(1) : "100.0";
    
    const gridPriceVal = (savings.grid_price_ct || 30.0).toFixed(1);
    const savingPerKwhCt = ((savings.grid_price_ct || 30.0) - (savings.feedin_price_ct || 7.0)).toFixed(1);

    const elEffectivePrice = document.getElementById("val-savings-effective-price");
    const elEffectiveSub = document.getElementById("val-savings-effective-sub");
    const elTotalCost = document.getElementById("val-savings-total-cost");
    const elTotalEur = document.getElementById("val-savings-total-eur");
    const elPvKwh = document.getElementById("val-savings-pv-kwh");
    const elGridKwh = document.getElementById("val-savings-grid-kwh");
    const elCo2 = document.getElementById("val-savings-co2-kg");
    const elAutarkyBadge = document.getElementById("badge-total-autarky");
    const elDeltaSub = document.getElementById("val-savings-delta-sub");
    const elPeriodText = document.getElementById("val-savings-period-text");
    const elHeaderPeriod = document.getElementById("val-savings-header-period");

    if (elEffectivePrice) elEffectivePrice.innerText = `${effectivePrice} ct/kWh`;
    if (elEffectiveSub) elEffectiveSub.innerText = `Statt ${gridPriceVal} ct/kWh Netzbezug`;
    if (elTotalCost) elTotalCost.innerText = `${totalCost} €`;
    if (elTotalEur) elTotalEur.innerText = `${totalEur} €`;
    if (elPvKwh) elPvKwh.innerText = `${pvKwh} kWh`;
    if (elGridKwh) elGridKwh.innerText = `${gridKwh} kWh`;
    if (elCo2) elCo2.innerText = `${co2Kg} kg`;
    if (elAutarkyBadge) elAutarkyBadge.innerHTML = `<i class="fa-solid fa-solar-panel"></i> ${autarkyPct}% PV-Autarkie`;
    if (elDeltaSub) elDeltaSub.innerText = `vs. Netzbezug (${savingPerKwhCt} ct/kWh Ersparnis)`;
    if (elPeriodText) elPeriodText.innerText = savings.period_str ? `Zeitraum: ${savings.period_str}` : "Zeitraum: Gesamt";
    if (elHeaderPeriod) elHeaderPeriod.innerHTML = savings.period_str ? `<i class="fa-regular fa-calendar"></i> Aufzeichnungszeitraum: ${savings.period_str}` : "";

    const inputGrid = document.getElementById("input-grid-price");
    const inputFeedin = document.getElementById("input-feedin-price");
    if (inputGrid && document.activeElement !== inputGrid && savings.grid_price_ct !== undefined) {
        inputGrid.value = savings.grid_price_ct;
    }
    if (inputFeedin && document.activeElement !== inputFeedin && savings.feedin_price_ct !== undefined) {
        inputFeedin.value = savings.feedin_price_ct;
    }

    renderSavingsBarChart(savings.daily_history || []);
    renderAutarkyDonutChart(savings.total_pv_kwh || 0, savings.total_grid_kwh || 0);
}

function renderSavingsBarChart(dailyHistory) {
    if (!dailyHistory || dailyHistory.length === 0) return;
    const canvas = document.getElementById("savingsBarChart");
    if (!canvas) return;

    const labels = dailyHistory.map(d => d.date_formatted);
    const pvData = dailyHistory.map(d => d.pv_kwh);
    const gridData = dailyHistory.map(d => d.grid_kwh);
    const eurData = dailyHistory.map(d => d.savings_eur);

    if (savingsBarChartInstance) {
        savingsBarChartInstance.data.labels = labels;
        savingsBarChartInstance.data.datasets[0].data = pvData;
        savingsBarChartInstance.data.datasets[1].data = gridData;
        savingsBarChartInstance.data.datasets[2].data = eurData;
        savingsBarChartInstance.update();
        return;
    }

    if (typeof Chart === 'undefined') return;

    const ctx = canvas.getContext("2d");
    savingsBarChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'PV-Sonnenstrom (kWh)',
                    data: pvData,
                    backgroundColor: 'rgba(0, 230, 118, 0.85)',
                    borderColor: '#00e676',
                    borderWidth: 1.5,
                    borderRadius: 4,
                    stack: 'car_energy',
                    order: 2
                },
                {
                    label: 'Netzstrom (kWh)',
                    data: gridData,
                    backgroundColor: 'rgba(255, 145, 0, 0.75)',
                    borderColor: '#ff9100',
                    borderWidth: 1.5,
                    borderRadius: 4,
                    stack: 'car_energy',
                    order: 2
                },
                {
                    label: 'Ersparnis (€)',
                    data: eurData,
                    type: 'line',
                    borderColor: '#ffd700',
                    backgroundColor: 'rgba(255, 215, 0, 0.2)',
                    borderWidth: 2.5,
                    pointBackgroundColor: '#ffd700',
                    pointRadius: 4,
                    yAxisID: 'y1',
                    order: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    display: true,
                    labels: { color: '#94a3b8', font: { family: 'Outfit', size: 11 } }
                },
                tooltip: {
                    callbacks: {
                        title: function(items) {
                            return `Tag: ${items[0].label}`;
                        },
                        label: function(ctx) {
                            if (ctx.dataset.label.includes('Ersparnis')) {
                                return `💰 PV-Ersparnis: ${ctx.raw.toFixed(2)} €`;
                            }
                            if (ctx.dataset.label.includes('PV-Sonnenstrom')) {
                                return `☀️ PV-Sonnenstrom: ${ctx.raw.toFixed(1)} kWh`;
                            }
                            if (ctx.dataset.label.includes('Netzstrom')) {
                                return `🔌 Netzbezug: ${ctx.raw.toFixed(1)} kWh`;
                            }
                            return `${ctx.dataset.label}: ${ctx.raw.toFixed(1)} kWh`;
                        },
                        footer: function(items) {
                            let totalKwh = 0;
                            items.forEach(item => {
                                if (item.dataset.type !== 'line') {
                                    totalKwh += item.raw;
                                }
                            });
                            return `⚡ Gesamt ins Auto geladen: ${totalKwh.toFixed(1)} kWh`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    stacked: true,
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8', font: { family: 'Outfit', size: 10 } }
                },
                y: {
                    stacked: true,
                    title: { display: true, text: 'Geladene Energie im Auto (kWh)', color: '#94a3b8' },
                    grid: { color: 'rgba(255, 255, 255, 0.08)' },
                    ticks: { color: '#94a3b8', font: { family: 'Outfit', size: 11 } }
                },
                y1: {
                    position: 'right',
                    title: { display: true, text: 'Ersparnis (€)', color: '#ffd700' },
                    grid: { drawOnChartArea: false },
                    ticks: {
                        color: '#ffd700',
                        font: { family: 'Outfit', size: 11 },
                        callback: function(val) { return val.toFixed(2) + ' €'; }
                    }
                }
            }
        }
    });
}

function renderAutarkyDonutChart(pvKwh, gridKwh) {
    const canvas = document.getElementById("autarkyDonutChart");
    if (!canvas) return;

    let displayPv = pvKwh;
    let displayGrid = gridKwh;
    if (pvKwh <= 0 && gridKwh <= 0) {
        displayPv = 100;
        displayGrid = 0;
    }

    if (autarkyDonutChartInstance) {
        autarkyDonutChartInstance.data.datasets[0].data = [displayPv, displayGrid];
        autarkyDonutChartInstance.update();
        return;
    }

    if (typeof Chart === 'undefined') return;

    const ctx = canvas.getContext("2d");
    autarkyDonutChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['PV Sonnenstrom', 'Zusatz-Netzstrom'],
            datasets: [{
                data: [displayPv, displayGrid],
                backgroundColor: ['#00e676', '#ff9100'],
                borderColor: ['rgba(0, 230, 118, 0.8)', 'rgba(255, 145, 0, 0.8)'],
                borderWidth: 2,
                hoverOffset: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#94a3b8', font: { family: 'Outfit', size: 11 } }
                },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                            const pct = total > 0 ? ((ctx.raw / total) * 100).toFixed(1) : 0;
                            return `${ctx.label}: ${ctx.raw.toFixed(1)} kWh (${pct}%)`;
                        }
                    }
                }
            },
            cutout: '70%'
        }
    });
}

function saveSavingsPrices() {
    const gridPrice = parseFloat(document.getElementById("input-grid-price").value) || 30.0;
    const feedinPrice = parseFloat(document.getElementById("input-feedin-price").value) || 7.0;

    fetch("/api/savings/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ grid_price_ct: gridPrice, feedin_price_ct: feedinPrice })
    })
    .then(res => res.json())
    .then(data => {
        if (data.savings) {
            updateSavingsUI(data.savings);
        }
    })
    .catch(err => console.error("Fehler beim Speichern der Preise:", err));
}

function syncVkwFeedinPrice() {
    fetch("/api/vkw_tariff")
        .then(res => res.json())
        .then(vkw => {
            if (vkw && vkw.current_price_ct !== undefined) {
                const currentVkwCt = vkw.current_price_ct.toFixed(1);
                document.getElementById("input-feedin-price").value = currentVkwCt;
                saveSavingsPrices();
            }
        })
        .catch(err => console.error("Fehler beim Abrufen des VKW Tarifs:", err));
}
