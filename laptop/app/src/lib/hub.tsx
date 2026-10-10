/** The live link to laptop/hub.py over WebSocket.
 *
 *  laptop -> app  {"type":"state", ...} about 10x a second   (see main.py hub.publish)
 *                 {"type":"event","text":"..."}               for the feed
 *  app -> laptop  {"action":"follow","on":true}, {"action":"radius_step","value":0.4}, ...
 *
 *  One provider at the root keeps the socket open across screens and reconnects by itself.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { useSettings } from '@/lib/settings';

export type InterpStatus = {
  url: string;
  stream: string;
  ok: boolean;
  model?: string;
  device?: string;
  backend?: string;
  multi?: number;
  fps_in?: number;
  fps_out?: number;
  interp_ms?: number;
  receiving?: boolean;
};

export type HubState = {
  mode: 'FOLLOW' | 'HOVER';
  state: string;
  flying: boolean;
  following: boolean;
  orbiting: boolean;
  orbit_dir: 1 | -1;
  watch: boolean;
  gentle: boolean;
  manual: boolean;
  dry_run: boolean;
  radius: number;
  d: number | null;
  bearing: number | null;
  heading: number | null;
  target: { x: number; y: number } | null;
  cmd: { lr: number; fb: number; ud: number; yaw: number };
  battery: number | null;
  brace: { ok: boolean; acc: number | null };
  glove: { ok: boolean; clutch: number };
  gps: { fix: number; sats: number; lat: number; lon: number; hacc: number } | null;
  lock: number | null;
  people: number;
  calib: { hfov: number; k_set: boolean; c_set: boolean };
  interp: InterpStatus | null;
  clients: number;
  t: number;
};

export type HubEvent = { id: number; t: number; text: string };

export type Action =
  | { action: 'radius'; value: number }
  | { action: 'radius_step'; value: number }
  | { action: 'follow' | 'orbit' | 'watch' | 'gentle'; on: boolean }
  | { action: 'orbit_dir'; value: 1 | -1 }
  | { action: 'takeoff' | 'land' | 'emergency' | 'relock' | 'yawtest' | 'cal_angle' | 'cal_dist' | 'cal_align' };

type Ctx = {
  /** socket open */
  connected: boolean;
  /** socket open AND a state packet arrived in the last 3 s */
  live: boolean;
  state: HubState | null;
  events: HubEvent[];
  send: (cmd: Action) => void;
  error: string | null;
};

const HubContext = createContext<Ctx | null>(null);
const RECONNECT_MS = 2000;
const STALE_S = 3;

export function HubProvider({ children }: { children: ReactNode }) {
  const { settings } = useSettings();
  const { host, wsPort } = settings;
  const [connected, setConnected] = useState(false);
  const [state, setState] = useState<HubState | null>(null);
  const [events, setEvents] = useState<HubEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(true);
  const wsRef = useRef<WebSocket | null>(null);
  const lastStateAt = useRef(0);
  const eventId = useRef(0);

  useEffect(() => {
    if (!host) return;
    let closed = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const open = () => {
      if (closed) return;
      const ws = new WebSocket(`ws://${host}:${wsPort}`);
      wsRef.current = ws;
      ws.onopen = () => {
        setConnected(true);
        setError(null);
      };
      ws.onmessage = (msg) => {
        let data: unknown;
        try {
          data = JSON.parse(String(msg.data));
        } catch {
          return;
        }
        if (!data || typeof data !== 'object') return;
        const packet = data as { type?: string; text?: string; t?: number };
        if (packet.type === 'state') {
          lastStateAt.current = Date.now();
          setStale(false);
          setState(packet as unknown as HubState);
        } else if (packet.type === 'event' && typeof packet.text === 'string') {
          const ev: HubEvent = { id: ++eventId.current, t: packet.t ?? Date.now() / 1000, text: packet.text };
          setEvents((prev) => [ev, ...prev].slice(0, 60));
        }
      };
      ws.onerror = () => setError(`Can't reach ${host}:${wsPort}`);
      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        if (!closed) timer = setTimeout(open, RECONNECT_MS);
      };
    };
    open();

    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [host, wsPort]);

  // 1 Hz check so `live` turns false when the laptop goes quiet
  useEffect(() => {
    const id = setInterval(() => setStale(Date.now() - lastStateAt.current > STALE_S * 1000), 1000);
    return () => clearInterval(id);
  }, []);

  const send = useCallback((cmd: Action) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(cmd));
  }, []);

  const live = connected && !stale;
  const value = useMemo<Ctx>(
    () => ({ connected, live, state, events, send, error }),
    [connected, live, state, events, send, error]
  );
  return <HubContext.Provider value={value}>{children}</HubContext.Provider>;
}

export function useHub() {
  const ctx = useContext(HubContext);
  if (!ctx) throw new Error('useHub must be used inside HubProvider');
  return ctx;
}
