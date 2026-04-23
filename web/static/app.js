const state = {
  devices: new Map(),
  alerts: [],
  selectedDevice: null,
  chart: null,
};

const deviceGrid = document.querySelector("#device-grid");
const deviceSelect = document.querySelector("#device-select");
const alertsEl = document.querySelector("#alerts");
const deviceCountEl = document.querySelector("#device-count");
const severeCountEl = document.querySelector("#severe-count");
const alertCountEl = document.querySelector("#alert-count");
const lastUpdateEl = document.querySelector("#last-update");
const wsDot = document.querySelector("#ws-dot");
const wsLabel = document.querySelector("#ws-label");

function percent(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`;
}

function formatTime(value) {
  if (!value) return "None";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString();
}

function setSocketStatus(status) {
  wsDot.className = `dot ${status}`;
  wsLabel.textContent =
    status === "online" ? "Live" : status === "offline" ? "Offline" : "Connecting";
}

function upsertDevice(device) {
  state.devices.set(device.device_id, device);
  if (!state.selectedDevice) {
    state.selectedDevice = device.device_id;
  }
  render();
}

function render() {
  const devices = [...state.devices.values()].sort((a, b) =>
    a.device_id.localeCompare(b.device_id),
  );
  const severeCount = devices.filter((device) => device.severe).length;
  const alertTotal = devices.reduce((total, device) => total + (device.alert_count || 0), 0);

  deviceCountEl.textContent = devices.length;
  severeCountEl.textContent = severeCount;
  alertCountEl.textContent = alertTotal;
  lastUpdateEl.textContent = devices.length ? `Updated ${new Date().toLocaleTimeString()}` : "No data";

  renderDeviceSelect(devices);
  renderDevices(devices);
  renderAlerts();
}

function renderDeviceSelect(devices) {
  const selectedStillExists = devices.some((device) => device.device_id === state.selectedDevice);
  if (!selectedStillExists) {
    state.selectedDevice = devices[0]?.device_id || null;
  }

  deviceSelect.innerHTML = devices
    .map(
      (device) =>
        `<option value="${device.device_id}" ${
          device.device_id === state.selectedDevice ? "selected" : ""
        }>${device.device_id}</option>`,
    )
    .join("");
}

function renderDevices(devices) {
  if (!devices.length) {
    deviceGrid.innerHTML = '<div class="empty">Waiting for log analysis data</div>';
    return;
  }

  deviceGrid.innerHTML = devices
    .map((device) => {
      const warn = percent(device.warn_ratio);
      const error = percent(device.error_ratio);
      const severeClass = device.severe ? "severe" : "";
      return `
        <article class="device-card ${severeClass}">
          <div class="device-title">
            <span>${device.device_id}</span>
            <span class="badge ${severeClass}">${device.severe ? "Severe" : "Normal"}</span>
          </div>
          <div class="bars">
            <div>
              <div class="bar-label"><span>WARN</span><strong>${warn}</strong></div>
              <div class="bar-track"><div class="bar-fill warn" style="width:${warn}"></div></div>
            </div>
            <div>
              <div class="bar-label"><span>ERROR</span><strong>${error}</strong></div>
              <div class="bar-track"><div class="bar-fill error" style="width:${error}"></div></div>
            </div>
          </div>
          <p class="latest">
            Latest ERROR: ${device.latest_error_message || "None"}<br />
            Time: ${formatTime(device.latest_error_timestamp)}<br />
            Window count: ${device.total_count}
          </p>
        </article>
      `;
    })
    .join("");
}

function renderAlerts() {
  if (!state.alerts.length) {
    alertsEl.innerHTML = '<div class="empty">No severe alerts</div>';
    return;
  }

  alertsEl.innerHTML = state.alerts
    .slice(0, 20)
    .map(
      (alert) => `
        <div class="alert-item">
          <strong>${alert.device_id} · ${percent(alert.error_ratio)}</strong>
          <span>${formatTime(alert.timestamp)} · ${alert.message}</span>
        </div>
      `,
    )
    .join("");
}

async function loadInitialData() {
  const [devices, alerts] = await Promise.all([
    fetch("/api/devices").then((response) => response.json()),
    fetch("/api/alerts").then((response) => response.json()),
  ]);
  devices.forEach(upsertDevice);
  state.alerts = alerts;
  render();
  await refreshTrend();
}

async function refreshTrend() {
  if (!state.selectedDevice) {
    renderTrend([]);
    return;
  }
  const response = await fetch(`/api/devices/${encodeURIComponent(state.selectedDevice)}/trend`);
  if (!response.ok) {
    renderTrend([]);
    return;
  }
  renderTrend(await response.json());
}

function renderTrend(rows) {
  if (!state.chart) {
    state.chart = echarts.init(document.querySelector("#trend-chart"));
    window.addEventListener("resize", () => state.chart.resize());
  }

  state.chart.setOption({
    color: ["#bd7f13", "#c43d34"],
    tooltip: { trigger: "axis" },
    grid: { left: 36, right: 18, top: 24, bottom: 36 },
    xAxis: {
      type: "category",
      data: rows.map((row) => formatTime(row.timestamp)),
      boundaryGap: false,
    },
    yAxis: { type: "value", minInterval: 1 },
    series: [
      {
        name: "WARN",
        type: "line",
        smooth: true,
        data: rows.map((row) => row.warn_count),
      },
      {
        name: "ERROR",
        type: "line",
        smooth: true,
        data: rows.map((row) => row.error_count),
      },
    ],
  });
}

function connectWebSocket() {
  setSocketStatus("connecting");
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/monitor`);

  socket.addEventListener("open", () => setSocketStatus("online"));
  socket.addEventListener("close", () => {
    setSocketStatus("offline");
    setTimeout(connectWebSocket, 2000);
  });
  socket.addEventListener("message", async (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "snapshot") {
      message.devices.forEach(upsertDevice);
      await refreshTrend();
    }
    if (message.type === "analysis") {
      upsertDevice(message.payload);
      if (message.payload.device_id === state.selectedDevice) {
        await refreshTrend();
      }
    }
    if (message.type === "alert") {
      state.alerts.unshift(message.payload);
      render();
    }
  });
}

deviceSelect.addEventListener("change", async (event) => {
  state.selectedDevice = event.target.value;
  await refreshTrend();
});

loadInitialData()
  .catch(() => {
    deviceGrid.innerHTML = '<div class="empty">Unable to load initial data</div>';
  })
  .finally(connectWebSocket);

