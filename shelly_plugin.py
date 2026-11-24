# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.orcaslicer.plugin]
# name = "Shelly Power Control"
# version = "1.2.0"
# description = "Control Shelly Gen 2/3 smart plugs, live power usage and energy statistics"
# ///

import json
import threading
import urllib.request
from collections import deque
from datetime import date
from pathlib import Path

import orca

CONFIG_PATH = Path.home() / ".orcaslicer_shelly_devices.json"
STATS_PATH = Path.home() / ".orcaslicer_shelly_stats.json"
POLL_INTERVAL_SEC = 3.0
HTTP_TIMEOUT_SEC = 1.5
HISTORY_POINTS = 30


def shelly_get_status(ip: str, switch_id: int = 0) -> dict:
    url = f"http://{ip}/rpc/Switch.GetStatus?id={switch_id}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return {
            "online": True,
            "on": bool(data.get("output", False)),
            "power": float(data.get("apower", 0.0)),
            "voltage": float(data.get("voltage", 0.0)),
            "current": float(data.get("current", 0.0)),
            "energy_kwh": float(data.get("aenergy", {}).get("total", 0.0)) / 1000.0,
        }


def shelly_set_power(ip: str, turn_on: bool, switch_id: int = 0) -> bool:
    state = "true" if turn_on else "false"
    url = f"http://{ip}/rpc/Switch.Set?id={switch_id}&on={state}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
        return resp.status == 200


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  body {
    font-family: var(--orca-font, system-ui, sans-serif);
    background: var(--orca-bg, #1e1e1e);
    color: var(--orca-fg, #e0e0e0);
    margin: 0;
    padding: 20px;
  }
  .header-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 14px;
    gap: 12px;
    flex-wrap: wrap;
  }
  h2 { margin: 0; }
  .lang-box {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.9em;
  }
  .toolbar {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
    margin-bottom: 16px;
    padding: 12px;
    border: 1px solid var(--orca-border, #444);
    border-radius: 6px;
  }
  .toolbar input, select {
    padding: 6px 10px;
    border-radius: 4px;
    border: 1px solid var(--orca-border, #555);
    background: var(--orca-bg, #252525);
    color: inherit;
  }
  .price-box {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.9em;
  }
  .price-box input { width: 68px; text-align: right; }
  .summary-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 10px;
    margin-bottom: 18px;
  }
  .stat-box {
    border: 1px solid var(--orca-border, #444);
    border-radius: 8px;
    padding: 12px;
  }
  .stat-label { font-size: 0.8em; opacity: 0.7; }
  .stat-val { font-size: 1.25em; font-weight: 700; margin-top: 4px; }
  .stat-sub { font-size: 0.85em; opacity: 0.8; margin-top: 2px; }
  .card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 12px;
  }
  .card {
    border: 1px solid var(--orca-border, #444);
    border-radius: 8px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-weight: 600;
    font-size: 1.05em;
  }
  .badge {
    font-size: 0.78em;
    padding: 2px 8px;
    border-radius: 12px;
    font-weight: 600;
  }
  .on { background: #1f6f3b; color: #fff; }
  .off { background: #555; color: #ddd; }
  .offline { background: #8b2626; color: #fff; }
  .metrics {
    font-size: 0.92em;
    display: flex;
    gap: 14px;
  }
  .stats-table {
    font-size: 0.84em;
    border-top: 1px solid var(--orca-border, #383838);
    padding-top: 8px;
    display: grid;
    grid-template-columns: 1fr auto auto;
    gap: 4px 12px;
    opacity: 0.9;
  }
  .sparkline {
    width: 100%;
    height: 36px;
    display: block;
    background: rgba(255,255,255,0.03);
    border-radius: 4px;
  }
  .actions {
    display: flex;
    gap: 8px;
    margin-top: 4px;
  }
  button {
    padding: 6px 12px;
    border-radius: 4px;
    cursor: pointer;
  }
</style>
</head>
<body>
  <div class="header-row">
    <h2 id="lblTitle">Shelly Power Control</h2>
    <div class="lang-box">
      <select id="langSelect" onchange="updateSettings()">
        <option value="cs">Čeština</option>
        <option value="en">English</option>
        <option value="de">Deutsch</option>
        <option value="es">Español</option>
        <option value="fr">Français</option>
        <option value="it">Italiano</option>
        <option value="pl">Polski</option>
        <option value="pt">Português</option>
        <option value="zh">中文</option>
        <option value="ja">日本語</option>
      </select>
      <select id="currencySelect" onchange="updateSettings()">
        <option value="Kč">Kč</option>
        <option value="€">€</option>
        <option value="$">$</option>
        <option value="£">£</option>
        <option value="zł">zł</option>
        <option value="¥">¥</option>
      </select>
    </div>
  </div>

  <div class="toolbar">
    <input id="devName" type="text" />
    <input id="devIp" type="text" />
    <button id="btnAdd" onclick="addDevice()"></button>
    <button id="btnRefresh" onclick="refreshNow()"></button>
    <div class="price-box">
      <label id="lblPrice" for="kwhPrice"></label>
      <input id="kwhPrice" type="number" step="0.01" min="0" value="6.0" onchange="updateSettings()" />
      <span id="lblPerKwh"></span>
    </div>
  </div>

  <div id="summaryGrid" class="summary-grid"></div>
  <div id="grid" class="card-grid"></div>

  <script>
    const I18N = {
      cs: {
        title: "Shelly Power Control",
        namePh: "Název (např. Snapmaker U1)",
        ipPh: "IP adresa (např. 192.168.1.50)",
        add: "Přidat zařízení",
        refresh: "Obnovit",
        price: "Cena:",
        perHour: "/ hod",
        empty: "Zatím nemáš přidané žádné Shelly zařízení.",
        on: "ZAPNUTO",
        off: "VYPNUTO",
        offline: "Offline",
        unavailable: "Nedostupné",
        turnOff: "Vypnout",
        turnOn: "Zapnout",
        remove: "Smazat",
        today: "Dnes",
        month: "Tento měsíc",
        totalShelly: "Celkem (Shelly)",
        sumPower: "Aktuální odběr celkem",
        sumToday: "Spotřeba dnes",
        sumMonth: "Spotřeba tento měsíc",
        sumTotal: "Celkem (všechna Shelly)"
      },
      en: {
        title: "Shelly Power Control",
        namePh: "Name (e.g. Snapmaker U1)",
        ipPh: "IP address (e.g. 192.168.1.50)",
        add: "Add device",
        refresh: "Refresh",
        price: "Price:",
        perHour: "/ hr",
        empty: "No Shelly devices added yet.",
        on: "ON",
        off: "OFF",
        offline: "Offline",
        unavailable: "Unavailable",
        turnOff: "Turn Off",
        turnOn: "Turn On",
        remove: "Delete",
        today: "Today",
        month: "This month",
        totalShelly: "Total (Shelly)",
        sumPower: "Total live power",
        sumToday: "Usage today",
        sumMonth: "Usage this month",
        sumTotal: "Total (all Shelly)"
      },
      de: {
        title: "Shelly Stromsteuerung",
        namePh: "Name (z.B. Snapmaker U1)",
        ipPh: "IP-Adresse (z.B. 192.168.1.50)",
        add: "Gerät hinzufügen",
        refresh: "Aktualisieren",
        price: "Preis:",
        perHour: "/ Std",
        empty: "Noch keine Shelly-Geräte hinzugefügt.",
        on: "EIN",
        off: "AUS",
        offline: "Offline",
        unavailable: "Nicht erreichbar",
        turnOff: "Ausschalten",
        turnOn: "Einschalten",
        remove: "Löschen",
        today: "Heute",
        month: "Dieser Monat",
        totalShelly: "Gesamt (Shelly)",
        sumPower: "Aktuelle Gesamtleistung",
        sumToday: "Verbrauch heute",
        sumMonth: "Verbrauch diesen Monat",
        sumTotal: "Gesamt (alle Shelly)"
      },
      es: {
        title: "Control de Energía Shelly",
        namePh: "Nombre (ej. Snapmaker U1)",
        ipPh: "Dirección IP (ej. 192.168.1.50)",
        add: "Añadir dispositivo",
        refresh: "Actualizar",
        price: "Precio:",
        perHour: "/ h",
        empty: "Aún no se han añadido dispositivos Shelly.",
        on: "ENCENDIDO",
        off: "APAGADO",
        offline: "Desconectado",
        unavailable: "No disponible",
        turnOff: "Apagar",
        turnOn: "Encender",
        remove: "Eliminar",
        today: "Hoy",
        month: "Este mes",
        totalShelly: "Total (Shelly)",
        sumPower: "Consumo actual total",
        sumToday: "Consumo hoy",
        sumMonth: "Consumo este mes",
        sumTotal: "Total (todos Shelly)"
      },
      fr: {
        title: "Contrôle d'Énergie Shelly",
        namePh: "Nom (ex. Snapmaker U1)",
        ipPh: "Adresse IP (ex. 192.168.1.50)",
        add: "Ajouter",
        refresh: "Actualiser",
        price: "Prix :",
        perHour: "/ h",
        empty: "Aucun appareil Shelly ajouté pour le moment.",
        on: "ALLUMÉ",
        off: "ÉTEINT",
        offline: "Hors ligne",
        unavailable: "Indisponible",
        turnOff: "Éteindre",
        turnOn: "Allumer",
        remove: "Supprimer",
        today: "Aujourd'hui",
        month: "Ce mois-ci",
        totalShelly: "Total (Shelly)",
        sumPower: "Puissance totale actuelle",
        sumToday: "Consommation aujourd'hui",
        sumMonth: "Consommation ce mois",
        sumTotal: "Total (tous Shelly)"
      },
      it: {
        title: "Controllo Energia Shelly",
        namePh: "Nome (es. Snapmaker U1)",
        ipPh: "Indirizzo IP (es. 192.168.1.50)",
        add: "Aggiungi dispositivo",
        refresh: "Aggiorna",
        price: "Prezzo:",
        perHour: "/ ora",
        empty: "Nessun dispositivo Shelly aggiunto.",
        on: "ACCESO",
        off: "SPENTO",
        offline: "Offline",
        unavailable: "Non disponibile",
        turnOff: "Spegni",
        turnOn: "Accendi",
        remove: "Elimina",
        today: "Oggi",
        month: "Questo mese",
        totalShelly: "Totale (Shelly)",
        sumPower: "Potenza attuale totale",
        sumToday: "Consumo oggi",
        sumMonth: "Consumo questo mese",
        sumTotal: "Totale (tutti Shelly)"
      },
      pl: {
        title: "Sterowanie Zasilaniem Shelly",
        namePh: "Nazwa (np. Snapmaker U1)",
        ipPh: "Adres IP (np. 192.168.1.50)",
        add: "Dodaj urządzenie",
        refresh: "Odśwież",
        price: "Cena:",
        perHour: "/ godz.",
        empty: "Nie dodano jeszcze żadnych urządzeń Shelly.",
        on: "WŁĄCZONE",
        off: "WYŁĄCZONE",
        offline: "Offline",
        unavailable: "Niedostępne",
        turnOff: "Wyłącz",
        turnOn: "Włącz",
        remove: "Usuń",
        today: "Dzisiaj",
        month: "Ten miesiąc",
        totalShelly: "Razem (Shelly)",
        sumPower: "Aktualny pobór łącznie",
        sumToday: "Zużycie dzisiaj",
        sumMonth: "Zużycie w tym miesiącu",
        sumTotal: "Razem (wszystkie Shelly)"
      },
      pt: {
        title: "Controle de Energia Shelly",
        namePh: "Nome (ex. Snapmaker U1)",
        ipPh: "Endereço IP (ex. 192.168.1.50)",
        add: "Adicionar",
        refresh: "Atualizar",
        price: "Preço:",
        perHour: "/ h",
        empty: "Nenhum dispositivo Shelly adicionado ainda.",
        on: "LIGADO",
        off: "DESLIGADO",
        offline: "Offline",
        unavailable: "Indisponível",
        turnOff: "Desligar",
        turnOn: "Ligar",
        remove: "Remover",
        today: "Hoje",
        month: "Este mês",
        totalShelly: "Total (Shelly)",
        sumPower: "Potência atual total",
        sumToday: "Consumo hoje",
        sumMonth: "Consumo este mês",
        sumTotal: "Total (todos Shelly)"
      },
      zh: {
        title: "Shelly 电源控制",
        namePh: "名称（例如 Snapmaker U1）",
        ipPh: "IP 地址（例如 192.168.1.50）",
        add: "添加设备",
        refresh: "刷新",
        price: "电价:",
        perHour: "/ 小时",
        empty: "尚未添加任何 Shelly 设备。",
        on: "已开启",
        off: "已关闭",
        offline: "离线",
        unavailable: "不可用",
        turnOff: "关闭",
        turnOn: "开启",
        remove: "删除",
        today: "今日",
        month: "本月",
        totalShelly: "累计 (Shelly)",
        sumPower: "当前总功率",
        sumToday: "今日用电",
        sumMonth: "本月用电",
        sumTotal: "总计（所有设备）"
      },
      ja: {
        title: "Shelly 電源コントロール",
        namePh: "名前（例: Snapmaker U1）",
        ipPh: "IPアドレス（例: 192.168.1.50）",
        add: "デバイス追加",
        refresh: "更新",
        price: "単価:",
        perHour: "/ 時間",
        empty: "Shelly デバイスがまだ追加されていません。",
        on: "オン",
        off: "オフ",
        offline: "オフライン",
        unavailable: "接続不可",
        turnOff: "オフにする",
        turnOn: "オンにする",
        remove: "削除",
        today: "今日",
        month: "今月",
        totalShelly: "累計 (Shelly)",
        sumPower: "現在の合計電力",
        sumToday: "今日の消費電力",
        sumMonth: "今月の消費電力",
        sumTotal: "合計（全デバイス）"
      }
    };

    let currentLang = "en";
    let currentCurrency = "Kč";
    let lastPayload = null;

    function detectBrowserLang() {
      const nav = (navigator.language || "en").slice(0, 2).toLowerCase();
      return I18N[nav] ? nav : "en";
    }

    function t(key) {
      return (I18N[currentLang] && I18N[currentLang][key]) || I18N.en[key] || key;
    }

    function applyStaticTranslations() {
      document.getElementById("lblTitle").textContent = t("title");
      document.getElementById("devName").placeholder = t("namePh");
      document.getElementById("devIp").placeholder = t("ipPh");
      document.getElementById("btnAdd").textContent = t("add");
      document.getElementById("btnRefresh").textContent = t("refresh");
      document.getElementById("lblPrice").textContent = t("price");
      document.getElementById("lblPerKwh").textContent = `${currentCurrency}/kWh`;
    }

    function buildSparkline(points) {
      if (!points || points.length < 2) return "";
      const w = 260, h = 36, pad = 3;
      const maxVal = Math.max(...points, 10);
      const step = (w - pad * 2) / (points.length - 1);
      const coords = points.map((v, i) => {
        const x = pad + i * step;
        const y = h - pad - ((v / maxVal) * (h - pad * 2));
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(" ");
      return `<svg class="sparkline" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        <polyline fill="none" stroke="#4ea8de" stroke-width="2" points="${coords}" />
      </svg>`;
    }

    function render(payload) {
      lastPayload = payload;
      const grid = document.getElementById("grid");
      const summaryGrid = document.getElementById("summaryGrid");
      const priceInput = document.getElementById("kwhPrice");
      const langSelect = document.getElementById("langSelect");
      const currSelect = document.getElementById("currencySelect");

      currentLang = (payload.lang && I18N[payload.lang]) ? payload.lang : detectBrowserLang();
      currentCurrency = payload.currency || "Kč";
      const price = Number(payload.price_czk ?? 6.0);

      if (document.activeElement !== langSelect) langSelect.value = currentLang;
      if (document.activeElement !== currSelect) currSelect.value = currentCurrency;
      if (document.activeElement !== priceInput) priceInput.value = price;

      applyStaticTranslations();

      const devices = payload.devices || [];
      const states = payload.states || {};
      const stats = payload.stats || {};
      const history = payload.history || {};

      if (!devices.length) {
        summaryGrid.innerHTML = "";
        grid.innerHTML = `<p>${t("empty")}</p>`;
        return;
      }

      let sumPower = 0, sumToday = 0, sumMonth = 0, sumTotal = 0;

      grid.innerHTML = devices.map(dev => {
        const st = states[dev.ip];
        const ds = stats[dev.ip] || { today_kwh: 0, month_kwh: 0, total_kwh: 0 };
        const pts = history[dev.ip] || [];

        sumToday += ds.today_kwh || 0;
        sumMonth += ds.month_kwh || 0;
        sumTotal += ds.total_kwh || 0;

        let badge = `<span class="badge offline">${t("offline")}</span>`;
        let metrics = `<span>${t("unavailable")}</span>`;
        let toggleBtn = "";

        if (st && st.online) {
          sumPower += st.power || 0;
          badge = st.on
            ? `<span class="badge on">${t("on")}</span>`
            : `<span class="badge off">${t("off")}</span>`;
          metrics = `
            <span><b>${st.power.toFixed(1)} W</b></span>
            <span>${st.voltage.toFixed(0)} V</span>
            <span>${st.current.toFixed(2)} A</span>
          `;
          toggleBtn = `<button onclick="toggleDevice('${dev.ip}', ${dev.switch_id || 0})">${st.on ? t("turnOff") : t("turnOn")}</button>`;
        }

        const todayKwh = (ds.today_kwh || 0);
        const monthKwh = (ds.month_kwh || 0);
        const totalKwh = (ds.total_kwh || 0);

        return `
          <div class="card">
            <div class="card-header">
              <span>${dev.name}</span>
              ${badge}
            </div>
            <div style="font-size:0.82em; opacity:0.65;">${dev.ip}</div>
            <div class="metrics">${metrics}</div>
            ${buildSparkline(pts)}
            <div class="stats-table">
              <span>${t("today")}</span><span>${todayKwh.toFixed(3)} kWh</span><span>${(todayKwh * price).toFixed(2)} ${currentCurrency}</span>
              <span>${t("month")}</span><span>${monthKwh.toFixed(2)} kWh</span><span>${(monthKwh * price).toFixed(1)} ${currentCurrency}</span>
              <span>${t("totalShelly")}</span><span>${totalKwh.toFixed(2)} kWh</span><span>${(totalKwh * price).toFixed(0)} ${currentCurrency}</span>
            </div>
            <div class="actions">
              ${toggleBtn}
              <button onclick="removeDevice('${dev.ip}')">${t("remove")}</button>
            </div>
          </div>
        `;
      }).join("");

      summaryGrid.innerHTML = `
        <div class="stat-box">
          <div class="stat-label">${t("sumPower")}</div>
          <div class="stat-val">${sumPower.toFixed(1)} W</div>
          <div class="stat-sub">${((sumPower / 1000) * price).toFixed(2)} ${currentCurrency} ${t("perHour")}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">${t("sumToday")}</div>
          <div class="stat-val">${sumToday.toFixed(3)} kWh</div>
          <div class="stat-sub">${(sumToday * price).toFixed(2)} ${currentCurrency}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">${t("sumMonth")}</div>
          <div class="stat-val">${sumMonth.toFixed(2)} kWh</div>
          <div class="stat-sub">${(sumMonth * price).toFixed(1)} ${currentCurrency}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">${t("sumTotal")}</div>
          <div class="stat-val">${sumTotal.toFixed(2)} kWh</div>
          <div class="stat-sub">${(sumTotal * price).toFixed(0)} ${currentCurrency}</div>
        </div>
      `;
    }

    function addDevice() {
      const nameEl = document.getElementById("devName");
      const ipEl = document.getElementById("devIp");
      if (!nameEl.value.trim() || !ipEl.value.trim()) return;
      window.orca.postMessage({ type: "add", name: nameEl.value.trim(), ip: ipEl.value.trim(), switch_id: 0 });
      nameEl.value = "";
      ipEl.value = "";
    }

    function removeDevice(ip) {
      window.orca.postMessage({ type: "remove", ip });
    }

    function toggleDevice(ip, switch_id) {
      window.orca.postMessage({ type: "toggle", ip, switch_id });
    }

    function refreshNow() {
      window.orca.postMessage({ type: "refresh" });
    }

    function updateSettings() {
      const val = parseFloat(document.getElementById("kwhPrice").value);
      const lang = document.getElementById("langSelect").value;
      const currency = document.getElementById("currencySelect").value;
      window.orca.postMessage({
        type: "set_settings",
        price_czk: isNaN(val) || val < 0 ? 0 : val,
        lang,
        currency
      });
    }

    window.orca.onMessage(msg => {
      if (msg && msg.type === "state") {
        render(msg);
      }
    });

    window.orca.postMessage({ type: "init" });
  </script>
</body>
</html>
"""


class ShellyPageCapability(orca.pages.PagesPluginCapabilityBase):
    def __init__(self):
        super().__init__()
        self.devices: list[dict] = load_json(CONFIG_PATH, [])
        self.stats_store: dict = load_json(STATS_PATH, {"price_czk": 6.0, "lang": "", "currency": "Kč", "devices": {}})
        if "devices" not in self.stats_store:
            self.stats_store = {"price_czk": 6.0, "lang": "", "currency": "Kč", "devices": {}}
        self.states: dict[str, dict] = {}
        self.power_history: dict[str, deque] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def get_name(self) -> str:
        return "Shelly"

    def get_ui(self) -> str:
        return HTML_PAGE

    def on_load(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def on_unload(self):
        self._stop_event.set()

    def _update_device_stats(self, ip: str, total_kwh: float) -> None:
        today_key = date.today().isoformat()
        month_key = today_key[:7]

        dev_stats = self.stats_store["devices"].setdefault(ip, {})
        changed = False

        if dev_stats.get("day_key") != today_key or total_kwh < dev_stats.get("day_base", total_kwh):
            dev_stats["day_key"] = today_key
            dev_stats["day_base"] = total_kwh
            changed = True

        if dev_stats.get("month_key") != month_key or total_kwh < dev_stats.get("month_base", total_kwh):
            dev_stats["month_key"] = month_key
            dev_stats["month_base"] = total_kwh
            changed = True

        dev_stats["last_total"] = total_kwh

        if changed:
            save_json(STATS_PATH, self.stats_store)

    def _compute_stats_view(self) -> dict:
        view = {}
        for ip, ds in self.stats_store.get("devices", {}).items():
            last_total = float(ds.get("last_total", 0.0))
            day_base = float(ds.get("day_base", last_total))
            month_base = float(ds.get("month_base", last_total))
            view[ip] = {
                "today_kwh": max(0.0, last_total - day_base),
                "month_kwh": max(0.0, last_total - month_base),
                "total_kwh": last_total,
            }
        return view

    def _push_state(self):
        with self._lock:
            payload = {
                "type": "state",
                "devices": list(self.devices),
                "states": dict(self.states),
                "stats": self._compute_stats_view(),
                "history": {ip: list(q) for ip, q in self.power_history.items()},
                "price_czk": float(self.stats_store.get("price_czk", 6.0)),
                "lang": str(self.stats_store.get("lang", "")),
                "currency": str(self.stats_store.get("currency", "Kč")),
            }
        try:
            self.post_message(payload)
        except Exception:
            pass

    def _poll_once(self):
        with self._lock:
            snapshot = list(self.devices)

        for dev in snapshot:
            ip = dev["ip"]
            sw_id = int(dev.get("switch_id", 0))
            try:
                st = shelly_get_status(ip, sw_id)
            except Exception:
                st = {"online": False, "on": False, "power": 0.0, "voltage": 0.0, "current": 0.0, "energy_kwh": 0.0}

            with self._lock:
                self.states[ip] = st
                if st["online"]:
                    self._update_device_stats(ip, st["energy_kwh"])
                    q = self.power_history.setdefault(ip, deque(maxlen=HISTORY_POINTS))
                    q.append(st["power"])

        self._push_state()

    def _poll_loop(self):
        while not self._stop_event.is_set():
            self._poll_once()
            self._stop_event.wait(POLL_INTERVAL_SEC)

    def _toggle_worker(self, ip: str, switch_id: int):
        with self._lock:
            current_on = self.states.get(ip, {}).get("on", False)
        try:
            shelly_set_power(ip, not current_on, switch_id)
            st = shelly_get_status(ip, switch_id)
            with self._lock:
                self.states[ip] = st
                if st["online"]:
                    self._update_device_stats(ip, st["energy_kwh"])
        except Exception:
            pass
        self._push_state()

    def on_message(self, data):
        if not isinstance(data, dict):
            return
        msg_type = data.get("type")

        if msg_type == "init":
            self._push_state()
        elif msg_type == "refresh":
            threading.Thread(target=self._poll_once, daemon=True).start()
        elif msg_type == "set_settings":
            try:
                price = max(0.0, float(data.get("price_czk", 6.0)))
                lang = str(data.get("lang", "")).strip()
                currency = str(data.get("currency", "Kč")).strip() or "Kč"
                with self._lock:
                    self.stats_store["price_czk"] = price
                    self.stats_store["lang"] = lang
                    self.stats_store["currency"] = currency
                    save_json(STATS_PATH, self.stats_store)
                self._push_state()
            except Exception:
                pass
        elif msg_type == "add":
            name = str(data.get("name", "")).strip()
            ip = str(data.get("ip", "")).strip()
            sw_id = int(data.get("switch_id", 0))
            if name and ip:
                with self._lock:
                    if not any(d["ip"] == ip and d.get("switch_id", 0) == sw_id for d in self.devices):
                        self.devices.append({"name": name, "ip": ip, "switch_id": sw_id})
                        save_json(CONFIG_PATH, self.devices)
                threading.Thread(target=self._poll_once, daemon=True).start()
        elif msg_type == "remove":
            ip = str(data.get("ip", "")).strip()
            with self._lock:
                self.devices = [d for d in self.devices if d["ip"] != ip]
                self.states.pop(ip, None)
                self.power_history.pop(ip, None)
                save_json(CONFIG_PATH, self.devices)
            self._push_state()
        elif msg_type == "toggle":
            ip = str(data.get("ip", "")).strip()
            sw_id = int(data.get("switch_id", 0))
            threading.Thread(target=self._toggle_worker, args=(ip, sw_id), daemon=True).start()


@orca.plugin
class ShellyPowerPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(ShellyPageCapability)