const BACKEND_URL = (import.meta.env.VITE_BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

function websocketUrl(path) {
  if (BACKEND_URL.startsWith("http://") || BACKEND_URL.startsWith("https://")) {
    return `${BACKEND_URL.replace(/^http/, "ws")}${path}`;
  }

  const base = typeof window === "undefined" ? "http://localhost" : window.location.origin;
  const url = new URL(`${BACKEND_URL}${path}`, base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export async function fetchLiveState({ signal } = {}) {
  const response = await fetch(`${BACKEND_URL}/grid/state`, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error(`/grid/state returned ${response.status}`);
  return response.json();
}

export async function runSimulation(scenario, duration_s = 400, { signal } = {}) {
  const response = await fetch(`${BACKEND_URL}/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ scenario, duration_s }),
    signal,
  });
  if (!response.ok) throw new Error(`/simulate returned ${response.status}`);
  return response.json();
}

export function connectLiveSocket(onSnapshot, onError) {
  if (typeof WebSocket === "undefined") return () => {};
  const wsUrl = websocketUrl("/ws/live");
  let socket;
  try {
    socket = new WebSocket(wsUrl);
  } catch (err) {
    onError?.(err);
    return () => {};
  }
  socket.addEventListener("message", (event) => {
    try {
      onSnapshot(JSON.parse(event.data));
    } catch (err) {
      onError?.(err);
    }
  });
  socket.addEventListener("error", (err) => onError?.(err));
  return () => {
    try { socket.close(); } catch { /* ignore */ }
  };
}
