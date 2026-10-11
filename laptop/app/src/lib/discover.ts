/** Find the laptop without typing an IP.
 *
 *  With the iPhone plugged in over USB and Personal Hotspot on, the phone is 172.20.10.1 and the
 *  laptop gets one of 172.20.10.2-14. We try a WebSocket to every one at once and keep the first
 *  that answers with a real hub state packet.
 */
const HOTSPOT = Array.from({ length: 13 }, (_, i) => `172.20.10.${i + 2}`);

function probe(host: string, port: number, timeoutMs: number): Promise<string | null> {
  return new Promise((resolve) => {
    let done = false;
    let ws: WebSocket | null = null;
    const finish = (result: string | null) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      try {
        ws?.close();
      } catch {}
      resolve(result);
    };
    const timer = setTimeout(() => finish(null), timeoutMs);
    try {
      ws = new WebSocket(`ws://${host}:${port}`);
    } catch {
      finish(null);
      return;
    }
    ws.onmessage = (msg) => {
      try {
        const p = JSON.parse(String(msg.data)) as { type?: string };
        if (p.type === 'state' || p.type === 'event') finish(host);
      } catch {}
    };
    ws.onerror = () => finish(null);
    ws.onclose = () => finish(null);
  });
}

/** Resolves to the laptop's address, or null if nothing answered. `extra` hosts are tried too. */
export async function findLaptop(port: number, extra: string[] = [], timeoutMs = 2500): Promise<string | null> {
  const candidates = Array.from(new Set([...extra.filter(Boolean), ...HOTSPOT]));
  return new Promise((resolve) => {
    let pending = candidates.length;
    let found = false;
    for (const host of candidates) {
      probe(host, port, timeoutMs).then((ok) => {
        pending--;
        if (ok && !found) {
          found = true;
          resolve(ok);
        } else if (pending === 0 && !found) {
          resolve(null);
        }
      });
    }
  });
}
