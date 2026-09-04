// Single shared WebSocket to the GnKAlgo backend ticker feed.
//
// One connection is shared across every LiveMarketTicker consumer (the frontend
// must have only one WebSocket to the backend for the ticker). Auth is via the
// httponly `gnk_access` cookie sent automatically by the browser; no provider
// token ever touches the frontend.

import type {
  ConnectionState,
  TickerMessage,
} from "@/services/market/tickerTypes";

type MessageHandler = (msg: TickerMessage) => void;
type StateHandler = (state: ConnectionState) => void;

// Exponential backoff with jitter: 1s, 2s, 4s, 8s, 15s, 30s (cap).
const BACKOFF_STEPS = [1000, 2000, 4000, 8000, 15000, 30000];

function wsBase(): string {
  if (typeof window === "undefined") return "";
  const host = window.location.hostname;
  if (host === "localhost" || host === "127.0.0.1") {
    const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return api.replace(/^http/, "ws");
  }
  // Prefer an explicit WS base if configured, else same-origin (nginx proxies /ws/).
  const configured = process.env.NEXT_PUBLIC_WS_URL;
  if (configured) return configured.replace(/^http/, "ws");
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}`;
}

class MarketTickerSocket {
  private ws: WebSocket | null = null;
  private messageHandlers = new Set<MessageHandler>();
  private stateHandlers = new Set<StateHandler>();
  private state: ConnectionState = "DISCONNECTED";
  private backoffIndex = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private stableTimer: ReturnType<typeof setTimeout> | null = null;
  private intentionalClose = false;
  private refCount = 0;

  onMessage(h: MessageHandler): () => void {
    this.messageHandlers.add(h);
    return () => this.messageHandlers.delete(h);
  }

  onState(h: StateHandler): () => void {
    this.stateHandlers.add(h);
    h(this.state);
    return () => this.stateHandlers.delete(h);
  }

  getState(): ConnectionState {
    return this.state;
  }

  private setState(s: ConnectionState) {
    this.state = s;
    this.stateHandlers.forEach((h) => h(s));
  }

  /** Acquire a shared reference; opens the socket on first consumer. */
  acquire(): () => void {
    this.refCount += 1;
    if (this.refCount === 1) this.connect();
    return () => this.release();
  }

  private release() {
    this.refCount = Math.max(0, this.refCount - 1);
    if (this.refCount === 0) this.disconnect();
  }

  private connect() {
    if (typeof window === "undefined") return;
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    this.intentionalClose = false;
    this.setState(this.backoffIndex === 0 ? "CONNECTING" : "RECONNECTING");
    try {
      this.ws = new WebSocket(`${wsBase()}/ws/market/ticker`);
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      // Cookie-based auth; message is a harmless no-op if the cookie is present.
      this.safeSend({ action: "auth" });
      this.setState("CONNECTED");
      // Reset backoff only after the connection stays up long enough to be stable.
      if (this.stableTimer) clearTimeout(this.stableTimer);
      this.stableTimer = setTimeout(() => {
        this.backoffIndex = 0;
      }, 30000);
    };

    this.ws.onmessage = (ev) => {
      let msg: TickerMessage | null = null;
      try {
        msg = JSON.parse(ev.data) as TickerMessage;
      } catch {
        return;
      }
      if (msg && typeof msg.type === "string") {
        this.messageHandlers.forEach((h) => h(msg as TickerMessage));
      }
    };

    this.ws.onclose = () => {
      if (this.stableTimer) clearTimeout(this.stableTimer);
      if (!this.intentionalClose) {
        this.setState("RECONNECTING");
        this.scheduleReconnect();
      } else {
        this.setState("DISCONNECTED");
      }
    };

    this.ws.onerror = () => {
      this.setState("ERROR");
    };
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return;
    const base = BACKOFF_STEPS[Math.min(this.backoffIndex, BACKOFF_STEPS.length - 1)];
    if (this.backoffIndex < BACKOFF_STEPS.length - 1) this.backoffIndex += 1;
    // Full jitter in [0.5*base, base] to avoid synchronized reconnect storms.
    const delay = Math.round(base * (0.5 + Math.random() * 0.5));
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.refCount > 0) this.connect();
    }, delay);
  }

  private disconnect() {
    this.intentionalClose = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.stableTimer) {
      clearTimeout(this.stableTimer);
      this.stableTimer = null;
    }
    if (this.ws) {
      try {
        this.ws.close();
      } catch {
        /* ignore */
      }
      this.ws = null;
    }
    this.backoffIndex = 0;
    this.setState("DISCONNECTED");
  }

  private safeSend(obj: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify(obj));
      } catch {
        /* ignore */
      }
    }
  }
}

export const marketTickerSocket = new MarketTickerSocket();
