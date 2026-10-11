/** Drone Leash simulator engine. Pure math, no UI.
 *
 *  World frame: meters, x to the right, y UP (north). Headings in degrees, clockwise from north,
 *  the same convention as the brace. The virtual drone runs the same leash idea as the laptop:
 *  a target point beside you, chosen by mode and radius, then it flies there. Here it also
 *  PATHFINDS around obstacles with A* on a grid, and keeps its camera on you.
 */

export type Vec = { x: number; y: number };
export type Rect = { x: number; y: number; w: number; h: number }; // bottom-left corner, meters
export type Mode = 'follow' | 'front' | 'orbit';

export type Scenario = {
  id: string;
  name: string;
  size: number; // arena side, meters
  obstacles: Rect[];
  start: Vec; // person start
  droneStart: Vec;
  blurb: string;
};

export const SCENARIOS: Scenario[] = [
  {
    id: 'field',
    name: 'Open field',
    size: 12,
    obstacles: [],
    start: { x: 6, y: 5 },
    droneStart: { x: 6, y: 2 },
    blurb: 'No obstacles. Learn how radius, follow and orbit behave.',
  },
  {
    id: 'corridor',
    name: 'Corridor',
    size: 12,
    obstacles: [
      { x: 0, y: 7.2, w: 5, h: 0.6 },
      { x: 7, y: 7.2, w: 5, h: 0.6 },
      { x: 0, y: 3.2, w: 3.5, h: 0.6 },
      { x: 5.5, y: 3.2, w: 6.5, h: 0.6 },
    ],
    start: { x: 6, y: 1.5 },
    droneStart: { x: 4, y: 1 },
    blurb: 'Walls with gaps. The drone must find the gap to stay with you.',
  },
  {
    id: 'pillars',
    name: 'Pillars',
    size: 12,
    obstacles: [3, 6, 9].flatMap((x) => [3, 6, 9].map((y) => ({ x: x - 0.35, y: y - 0.35, w: 0.7, h: 0.7 }))),
    start: { x: 1.5, y: 1.5 },
    droneStart: { x: 1.5, y: 4 },
    blurb: 'A grid of columns. Watch the path bend around them.',
  },
  {
    id: 'warehouse',
    name: 'Warehouse',
    size: 12,
    obstacles: [
      { x: 2, y: 1.5, w: 1, h: 4 },
      { x: 5, y: 1.5, w: 1, h: 4 },
      { x: 8, y: 1.5, w: 1, h: 4 },
      { x: 2, y: 7, w: 1, h: 4 },
      { x: 5, y: 7, w: 1, h: 4 },
      { x: 8, y: 7, w: 1, h: 4 },
    ],
    start: { x: 0.8, y: 0.8 },
    droneStart: { x: 0.8, y: 3 },
    blurb: 'Shelf aisles. Line of sight breaks often; see it recover.',
  },
];

export const SIM = {
  cell: 0.25, // A* grid cell, meters
  droneRadius: 0.35, // obstacle inflation
  droneSpeed: 1.6, // m/s max
  droneAccel: 2.5, // m/s^2
  droneTurnRate: 180, // deg/s
  personSpeed: 1.2, // m/s
  personTurnRate: 120, // deg/s (on-screen turning)
  hfov: 70, // camera field of view, degrees
  dMin: 1.0, // never closer than this
  orbitRate: 40, // deg/s around you
  replanEvery: 0.25, // s
  nearMiss: 0.55, // m from an obstacle counts as a close call
};

export type Drone = { pos: Vec; yaw: number; vel: Vec };
export type Person = { pos: Vec; heading: number };

export type Score = {
  seconds: number;
  inFrameSeconds: number;
  closeCalls: number;
  pathMeters: number;
};

export type World = {
  scenario: Scenario;
  person: Person;
  drone: Drone;
  mode: Mode;
  radius: number;
  orbitDir: 1 | -1;
  orbitAngle: number; // deg, where on the circle the orbit target is (clockwise from north, from you)
  target: Vec;
  path: Vec[]; // waypoints from the drone to the target
  inFrame: boolean; // camera sees you (angle + line of sight)
  lineOfSight: boolean;
  score: Score;
  running: boolean;
  lastReplan: number;
  inCloseCall: boolean;
  grid: Uint8Array; // 1 = blocked (inflated)
  cells: number;
};

// ---------------------------------------------------------------- helpers
export const wrap180 = (a: number) => ((((a + 180) % 360) + 360) % 360) - 180;
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
const dist = (a: Vec, b: Vec) => Math.hypot(a.x - b.x, a.y - b.y);
/** unit vector of a heading (clockwise from north) */
const dirOf = (headingDeg: number): Vec => ({ x: Math.sin((headingDeg * Math.PI) / 180), y: Math.cos((headingDeg * Math.PI) / 180) });
/** heading (clockwise from north) from a to b */
export const bearing = (a: Vec, b: Vec) => (Math.atan2(b.x - a.x, b.y - a.y) * 180) / Math.PI;

function distToRect(p: Vec, r: Rect) {
  const dx = Math.max(r.x - p.x, 0, p.x - (r.x + r.w));
  const dy = Math.max(r.y - p.y, 0, p.y - (r.y + r.h));
  return Math.hypot(dx, dy);
}

export function nearestObstacle(p: Vec, s: Scenario) {
  let best = Infinity;
  for (const r of s.obstacles) best = Math.min(best, distToRect(p, r));
  // arena walls
  best = Math.min(best, p.x, p.y, s.size - p.x, s.size - p.y);
  return best;
}

function buildGrid(s: Scenario) {
  const cells = Math.round(s.size / SIM.cell);
  const grid = new Uint8Array(cells * cells);
  for (let j = 0; j < cells; j++) {
    for (let i = 0; i < cells; i++) {
      const p = { x: (i + 0.5) * SIM.cell, y: (j + 0.5) * SIM.cell };
      if (nearestObstacle(p, s) < SIM.droneRadius) grid[j * cells + i] = 1;
    }
  }
  return { grid, cells };
}

function toCell(p: Vec, w: World) {
  return { i: clamp(Math.floor(p.x / SIM.cell), 0, w.cells - 1), j: clamp(Math.floor(p.y / SIM.cell), 0, w.cells - 1) };
}

/** Nearest free cell to a point (the target may sit inside a wall). */
function nearestFree(p: Vec, w: World) {
  const c = toCell(p, w);
  if (!w.grid[c.j * w.cells + c.i]) return c;
  for (let ring = 1; ring < 12; ring++) {
    for (let dj = -ring; dj <= ring; dj++) {
      for (let di = -ring; di <= ring; di++) {
        if (Math.max(Math.abs(di), Math.abs(dj)) !== ring) continue;
        const i = c.i + di, j = c.j + dj;
        if (i < 0 || j < 0 || i >= w.cells || j >= w.cells) continue;
        if (!w.grid[j * w.cells + i]) return { i, j };
      }
    }
  }
  return c;
}

// ---------------------------------------------------------------- A*
export function astar(w: World, from: Vec, to: Vec): Vec[] {
  const n = w.cells;
  const s = nearestFree(from, w);
  const g = nearestFree(to, w);
  const key = (i: number, j: number) => j * n + i;
  const start = key(s.i, s.j), goal = key(g.i, g.j);
  if (start === goal) return [to];

  const gScore = new Float32Array(n * n).fill(Infinity);
  const came = new Int32Array(n * n).fill(-1);
  const closed = new Uint8Array(n * n);
  const h = (k: number) => {
    const i = k % n, j = Math.floor(k / n);
    const di = Math.abs(i - g.i), dj = Math.abs(j - g.j);
    return Math.max(di, dj) + (Math.SQRT2 - 1) * Math.min(di, dj); // octile
  };
  // binary heap of [f, key]
  const heap: number[][] = [];
  const push = (f: number, k: number) => {
    heap.push([f, k]);
    let c = heap.length - 1;
    while (c > 0) {
      const p = (c - 1) >> 1;
      if (heap[p][0] <= heap[c][0]) break;
      [heap[p], heap[c]] = [heap[c], heap[p]];
      c = p;
    }
  };
  const pop = () => {
    const top = heap[0];
    const last = heap.pop()!;
    if (heap.length) {
      heap[0] = last;
      let c = 0;
      for (;;) {
        const l = 2 * c + 1, r = l + 1;
        let m = c;
        if (l < heap.length && heap[l][0] < heap[m][0]) m = l;
        if (r < heap.length && heap[r][0] < heap[m][0]) m = r;
        if (m === c) break;
        [heap[m], heap[c]] = [heap[c], heap[m]];
        c = m;
      }
    }
    return top;
  };

  gScore[start] = 0;
  push(h(start), start);
  const dirs = [[1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1], [1, 1, Math.SQRT2], [1, -1, Math.SQRT2], [-1, 1, Math.SQRT2], [-1, -1, Math.SQRT2]];
  let found = false;
  while (heap.length) {
    const [, k] = pop();
    if (closed[k]) continue;
    if (k === goal) { found = true; break; }
    closed[k] = 1;
    const i = k % n, j = Math.floor(k / n);
    for (const [di, dj, cost] of dirs) {
      const ni = i + di, nj = j + dj;
      if (ni < 0 || nj < 0 || ni >= n || nj >= n) continue;
      const nk = key(ni, nj);
      if (w.grid[nk] || closed[nk]) continue;
      if (di && dj && (w.grid[key(i + di, j)] || w.grid[key(i, j + dj)])) continue; // no corner cutting
      const t = gScore[k] + cost;
      if (t < gScore[nk]) {
        gScore[nk] = t;
        came[nk] = k;
        push(t + h(nk), nk);
      }
    }
  }
  if (!found) return [];
  const cellsPath: number[] = [];
  for (let k = goal; k !== -1; k = came[k]) cellsPath.push(k);
  cellsPath.reverse();
  // cell centers, then the exact target as the last point; drop the first (the drone's own cell)
  const pts = cellsPath.slice(1).map((k) => ({ x: ((k % n) + 0.5) * SIM.cell, y: (Math.floor(k / n) + 0.5) * SIM.cell }));
  pts.push(to);
  return simplify(pts, w);
}

/** Remove waypoints the drone can fly straight past (string pulling), keeping the path short and smooth. */
function simplify(pts: Vec[], w: World) {
  if (pts.length < 3) return pts;
  const out: Vec[] = [pts[0]];
  let anchor = pts[0];
  for (let i = 2; i < pts.length; i++) {
    if (!clearLine(anchor, pts[i], w)) {
      anchor = pts[i - 1];
      out.push(anchor);
    }
  }
  out.push(pts[pts.length - 1]);
  return out;
}

/** True when the straight segment a->b stays out of (inflated) obstacles. */
export function clearLine(a: Vec, b: Vec, w: World) {
  const steps = Math.ceil(dist(a, b) / (SIM.cell * 0.5)) || 1;
  for (let k = 0; k <= steps; k++) {
    const p = { x: a.x + ((b.x - a.x) * k) / steps, y: a.y + ((b.y - a.y) * k) / steps };
    const c = toCell(p, w);
    if (w.grid[c.j * w.cells + c.i]) return false;
  }
  return true;
}

/** Line of sight for the camera: the real geometry, not the inflated grid. */
export function canSee(a: Vec, b: Vec, s: Scenario) {
  const steps = Math.ceil(dist(a, b) / 0.1) || 1;
  for (let k = 0; k <= steps; k++) {
    const p = { x: a.x + ((b.x - a.x) * k) / steps, y: a.y + ((b.y - a.y) * k) / steps };
    for (const r of s.obstacles) if (p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h) return false;
  }
  return true;
}

// ---------------------------------------------------------------- world
export function createWorld(scenario: Scenario, radius = 2.5, mode: Mode = 'follow'): World {
  const { grid, cells } = buildGrid(scenario);
  const w: World = {
    scenario,
    person: { pos: { ...scenario.start }, heading: 0 },
    drone: { pos: { ...scenario.droneStart }, yaw: 0, vel: { x: 0, y: 0 } },
    mode,
    radius,
    orbitDir: 1,
    orbitAngle: 180,
    target: { ...scenario.droneStart },
    path: [],
    inFrame: false,
    lineOfSight: true,
    score: { seconds: 0, inFrameSeconds: 0, closeCalls: 0, pathMeters: 0 },
    running: false,
    lastReplan: -1,
    inCloseCall: false,
    grid,
    cells,
  };
  w.drone.yaw = bearing(w.drone.pos, w.person.pos);
  w.orbitAngle = bearing(w.person.pos, w.drone.pos);
  return w;
}

/** The leash target for the current mode: the same idea as leash.target_point on the laptop. */
export function leashTarget(w: World): Vec {
  const p = w.person.pos, r = w.radius;
  if (w.mode === 'front') {
    const f = dirOf(w.person.heading); // r meters ahead of you, where you're facing
    return { x: p.x + r * f.x, y: p.y + r * f.y };
  }
  if (w.mode === 'orbit') {
    const f = dirOf(w.orbitAngle);
    return { x: p.x + r * f.x, y: p.y + r * f.y };
  }
  // follow: keep the radius along the line from you to the drone
  const dx = w.drone.pos.x - p.x, dy = w.drone.pos.y - p.y;
  const len = Math.hypot(dx, dy) || 1;
  return { x: p.x + (r * dx) / len, y: p.y + (r * dy) / len };
}

export type Input = {
  walk: -1 | 0 | 1; // back / none / forward (relative to facing)
  strafe: -1 | 0 | 1; // left / none / right
  turn: -1 | 0 | 1; // on-screen turning; ignored when a brace heading is given
  braceHeading: number | null; // live heading from the real brace, if any
};

/** Advance the world by dt seconds. */
export function step(w: World, dt: number, input: Input, now: number) {
  if (!w.running) return;
  const s = w.scenario;

  // --- you ---
  const you = w.person;
  if (input.braceHeading !== null) you.heading = input.braceHeading;
  else you.heading = wrap180(you.heading + input.turn * SIM.personTurnRate * dt);
  const f = dirOf(you.heading);
  const right = { x: f.y, y: -f.x };
  const nx = you.pos.x + (input.walk * f.x + input.strafe * right.x) * SIM.personSpeed * dt;
  const ny = you.pos.y + (input.walk * f.y + input.strafe * right.y) * SIM.personSpeed * dt;
  if (nearestObstacle({ x: nx, y: ny }, s) > 0.3) you.pos = { x: clamp(nx, 0.3, s.size - 0.3), y: clamp(ny, 0.3, s.size - 0.3) };

  // --- the leash target, pathfinding ---
  if (w.mode === 'orbit') w.orbitAngle = wrap180(w.orbitAngle + w.orbitDir * SIM.orbitRate * dt);
  w.target = leashTarget(w);
  if (now - w.lastReplan >= SIM.replanEvery) {
    w.lastReplan = now;
    w.path = astar(w, w.drone.pos, w.target);
  }

  // --- the drone: fly the path, keep the camera on you ---
  const d = w.drone;
  const next = w.path.length ? w.path[0] : w.target;
  const toNext = { x: next.x - d.pos.x, y: next.y - d.pos.y };
  const dNext = Math.hypot(toNext.x, toNext.y);
  const dTarget = dist(d.pos, w.target);
  const tooClose = dist(d.pos, you.pos) < SIM.dMin;
  let want: Vec;
  if (tooClose) {
    const away = bearing(you.pos, d.pos);
    const a = dirOf(away);
    want = { x: a.x * SIM.droneSpeed * 0.6, y: a.y * SIM.droneSpeed * 0.6 };
  } else if (dTarget < 0.2) {
    want = { x: 0, y: 0 };
  } else {
    const speed = Math.min(SIM.droneSpeed, dTarget * 1.5);
    want = dNext > 1e-6 ? { x: (toNext.x / dNext) * speed, y: (toNext.y / dNext) * speed } : { x: 0, y: 0 };
  }
  const maxDv = SIM.droneAccel * dt;
  const dvx = clamp(want.x - d.vel.x, -maxDv, maxDv), dvy = clamp(want.y - d.vel.y, -maxDv, maxDv);
  d.vel = { x: d.vel.x + dvx, y: d.vel.y + dvy };
  const px = d.pos.x + d.vel.x * dt, py = d.pos.y + d.vel.y * dt;
  if (nearestObstacle({ x: px, y: py }, s) > SIM.droneRadius * 0.6) {
    w.score.pathMeters += Math.hypot(px - d.pos.x, py - d.pos.y);
    d.pos = { x: clamp(px, 0.2, s.size - 0.2), y: clamp(py, 0.2, s.size - 0.2) };
  } else {
    d.vel = { x: 0, y: 0 };
  }
  if (w.path.length && dNext < 0.3) w.path.shift();

  // camera: turn toward you, as fast as the Tello would
  const wantYaw = bearing(d.pos, you.pos);
  const err = wrap180(wantYaw - d.yaw);
  d.yaw = wrap180(d.yaw + clamp(err, -SIM.droneTurnRate * dt, SIM.droneTurnRate * dt));

  // --- framing and score ---
  w.lineOfSight = canSee(d.pos, you.pos, s);
  w.inFrame = w.lineOfSight && Math.abs(wrap180(wantYaw - d.yaw)) < SIM.hfov / 2;
  w.score.seconds += dt;
  if (w.inFrame) w.score.inFrameSeconds += dt;
  const near = nearestObstacle(d.pos, s) < SIM.nearMiss;
  if (near && !w.inCloseCall) w.score.closeCalls += 1;
  w.inCloseCall = near;
}

export function framePercent(w: World) {
  return w.score.seconds > 0 ? Math.round((100 * w.score.inFrameSeconds) / w.score.seconds) : 0;
}
