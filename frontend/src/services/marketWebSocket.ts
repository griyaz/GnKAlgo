type TickHandler = (tick: { symbol: string; ltp: number; time: number }) => void;
type StatusHandler = (status: string) => void;

function wsBase(): string {
  if (typeof window === "undefined") return "";
  const host = window.location.hostname;
  if (host === "localhost" || host === "127.0.0.1") {
    const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return api.replace(/^http/, "ws");
  }
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}`;
}

class MarketWebSocket {
  private ws: WebSocket | null = null;
  private tickHandlers = new Set<TickHandler>();
  private statusHandlers = new Set<StatusHandler>();
  private status = "DISCONNECTED";
  private reconnectDelay = 1000;
  private maxDelay = 16000;
  private subscribed: { symbol: string; exchange: string } | null = null;
  private intentionalClose = false;

  onTick(h: TickHandler) {
    this.tickHandlers.add(h);
    return () => {
      this.tickHandlers.delete(h);
    };
  }

  onStatus(h: StatusHandler) {
    this.statusHandlers.add(h);
    return () => {
      this.statusHandlers.delete(h);
    };
  }

  private setStatus(s: string) {
    this.status = s;
    this.statusHandlers.forEach((h) => h(s));
  }

  connect() {
    this.intentionalClose = false;
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    this.setStatus("CONNECTING");
    const url = `${wsBase()}/api/v1/market/ws`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.reconnectDelay = 1000;
      this.setStatus("CONNECTED");
      this.send({ action: "auth" });
      if (this.subscribed) {
        this.sendSubscribe(this.subscribed.symbol, this.subscribed.exchange);
      }
    };

    this.ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "tick" && data.ltp != null) {
          this.tickHandlers.forEach((h) =>
            h({ symbol: data.symbol, ltp: data.ltp, time: data.time }),
          );
        }
      } catch {
        /* ignore */
      }
    };

    this.ws.onclose = () => {
      this.ws = null;
      this.setStatus("DISCONNECTED");
      if (!this.intentionalClose) this.scheduleReconnect();
    };

    this.ws.onerror = () => {
      this.setStatus("ERROR");
    };
  }

  private scheduleReconnect() {
    this.setStatus("RECONNECTING");
    setTimeout(() => {
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxDelay);
      this.connect();
    }, this.reconnectDelay);
  }

  disconnect() {
    this.intentionalClose = true;
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.setStatus("DISCONNECTED");
  }

  private send(msg: object) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  private sendSubscribe(symbol: string, exchange: string) {
    this.send({ action: "subscribe", symbol, exchange });
  }

  subscribe(symbol: string, exchange: string) {
    this.subscribed = { symbol, exchange };
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.sendSubscribe(symbol, exchange);
    } else {
      this.connect();
    }
  }

  unsubscribe(symbol: string) {
    this.send({ action: "unsubscribe", symbol });
    if (this.subscribed?.symbol === symbol) this.subscribed = null;
  }

  getStatus() {
    return this.status;
  }
}

export const marketWebSocket = new MarketWebSocket();
