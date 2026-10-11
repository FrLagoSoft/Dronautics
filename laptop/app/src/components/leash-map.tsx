/** Top-down map, same picture as hud.draw_map on the laptop:
 *  drone at the bottom pointing up, you (white), the leash circle, the target (blue), the brace leg (orange). */
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Line, Path, Polygon, Rect } from 'react-native-svg';

import { Palette, Radius } from '@/constants/palette';
import type { HubState } from '@/lib/hub';

type Props = { state: HubState | null; size: number };
type Cmd = HubState['cmd'] | null;

const MOVE_MIN = 3; // rc commands this small are noise, not movement
const ARROW_PX = 60; // arrow length at full speed (rc 50)

/** Arrow from the drone in the direction it's flying, longer when faster. */
function movementArrow(cmd: Cmd, ox: number, oy: number) {
  if (!cmd) return null;
  const { lr, fb } = cmd;
  const mag = Math.hypot(lr, fb);
  if (mag < MOVE_MIN) return null;
  const len = Math.min(ARROW_PX, 14 + (mag / 50) * (ARROW_PX - 14));
  const ux = lr / mag, uy = -fb / mag; // screen: right = +x, forward = up = -y
  const x = ox + ux * len, y = oy + uy * len;
  const px = -uy, py = ux; // perpendicular, for the arrowhead
  const head = `${x + ux * 8},${y + uy * 8} ${x + px * 6},${y + py * 6} ${x - px * 6},${y - py * 6}`;
  return { x, y, head };
}

/** A short arc around the drone with an arrowhead: which way it's turning. */
function turnArc(cmd: Cmd, ox: number, oy: number) {
  if (!cmd || Math.abs(cmd.yaw) < MOVE_MIN) return null;
  const R = 20, dir = cmd.yaw > 0 ? 1 : -1;
  const sweep = Math.min(150, 40 + Math.abs(cmd.yaw) * 1.2) * dir; // degrees, longer arc = faster turn
  const at = (deg: number) => ({ x: ox + R * Math.sin((deg * Math.PI) / 180), y: oy - R * Math.cos((deg * Math.PI) / 180) });
  const a = at(0), b = at(sweep);
  const arc = `M ${a.x} ${a.y} A ${R} ${R} 0 ${Math.abs(sweep) > 180 ? 1 : 0} ${dir > 0 ? 1 : 0} ${b.x} ${b.y}`;
  // arrowhead tangent to the circle at the end of the arc
  const t = ((sweep * Math.PI) / 180);
  const tx = Math.cos(t) * dir, ty = Math.sin(t) * dir; // tangent direction (screen coords)
  const nx = Math.sin(t), ny = -Math.cos(t); // outward normal
  const head = `${b.x + tx * 7},${b.y + ty * 7} ${b.x + nx * 5},${b.y + ny * 5} ${b.x - nx * 5},${b.y - ny * 5}`;
  return { arc, head };
}

export function LeashMap({ state, size }: Props) {
  const ox = size / 2;
  const oy = size - 28;
  const d = state?.d ?? null;
  const b = state?.bearing ?? null;
  const r = state?.radius ?? 2.5;
  const target = state?.target ?? null;

  // auto-fit: the farthest thing we draw stays inside the panel
  let reach = r + 1;
  if (d !== null) reach = Math.max(reach, d + r + 0.3);
  if (target) reach = Math.max(reach, Math.hypot(target.x, target.y) + 0.5);
  const scale = Math.min(48, Math.max(14, (size - 40) / reach));

  // x forward (up on screen), y right
  const pt = (xFwd: number, yRight: number) => ({ x: ox + yRight * scale, y: oy - xFwd * scale });

  let person: { x: number; y: number } | null = null;
  if (d !== null && b !== null) {
    const rad = (b * Math.PI) / 180;
    person = pt(d * Math.cos(rad), d * Math.sin(rad));
  }
  const tgt = target ? pt(target.x, target.y) : null;

  // the command the laptop is sending right now (rc -100..100): forward/back = fb, sideways = lr, turn = yaw
  const cmd = state?.cmd ?? null;
  const move = movementArrow(cmd, ox, oy);
  const turn = turnArc(cmd, ox, oy);

  return (
    <View style={[styles.panel, { width: size, height: size }]}>
      <Svg width={size} height={size}>
        <Rect x={0} y={0} width={size} height={size} fill={Palette.ink} />
        {/* range rings every metre */}
        {[1, 2, 3, 4, 5, 6].map((m) =>
          m * scale < size ? (
            <Circle key={m} cx={ox} cy={oy} r={m * scale} stroke={Palette.inkSoft} strokeWidth={1} fill="none" />
          ) : null
        )}
        <Line x1={ox} y1={oy} x2={ox} y2={8} stroke={Palette.inkSoft} strokeWidth={1} />
        {person ? (
          <>
            <Circle cx={person.x} cy={person.y} r={r * scale} stroke={Palette.mute} strokeWidth={1} fill="none" />
            <Line x1={ox} y1={oy} x2={person.x} y2={person.y} stroke={Palette.mute} strokeWidth={1} />
            {tgt ? (
              <>
                <Line x1={person.x} y1={person.y} x2={tgt.x} y2={tgt.y} stroke={Palette.orange} strokeWidth={2.5} />
                <Line x1={ox} y1={oy} x2={tgt.x} y2={tgt.y} stroke={Palette.blue} strokeWidth={2} />
                <Circle cx={tgt.x} cy={tgt.y} r={6} stroke={Palette.blue} strokeWidth={2} fill="none" />
              </>
            ) : null}
            <Circle cx={person.x} cy={person.y} r={6} fill={Palette.cream} />
          </>
        ) : null}
        {/* where the drone is moving right now: green arrow (forward = up, right = right), arc = turning */}
        {move ? (
          <>
            <Line x1={ox} y1={oy} x2={move.x} y2={move.y} stroke={Palette.ok} strokeWidth={3} strokeLinecap="round" />
            <Polygon points={move.head} fill={Palette.ok} />
          </>
        ) : null}
        {turn ? <Path d={turn.arc} stroke={Palette.ok} strokeWidth={2.5} fill="none" strokeLinecap="round" /> : null}
        {turn ? <Polygon points={turn.head} fill={Palette.ok} /> : null}
        {/* the drone, nose up */}
        <Polygon
          points={`${ox},${oy - 10} ${ox - 8},${oy + 7} ${ox + 8},${oy + 7}`}
          fill={Palette.cream}
          stroke={Palette.cream}
          strokeWidth={1.5}
        />
      </Svg>
      {cmd && cmd.ud !== 0 ? <Text style={styles.ud}>{cmd.ud > 0 ? '▲ up' : '▼ down'}</Text> : null}
      <Text style={styles.caption}>
        {person ? `1 m = ${scale.toFixed(0)} px` : state ? 'no person yet' : 'no link'}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { borderRadius: Radius.panel, overflow: 'hidden', backgroundColor: Palette.ink },
  caption: { position: 'absolute', left: 12, bottom: 8, color: Palette.mute, fontSize: 11 },
  ud: { position: 'absolute', right: 12, bottom: 8, color: Palette.ok, fontSize: 12, fontWeight: '700' },
});
