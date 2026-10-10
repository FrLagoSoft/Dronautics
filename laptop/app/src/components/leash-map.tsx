/** Top-down map, same picture as hud.draw_map on the laptop:
 *  drone at the bottom pointing up, you (white), the leash circle, the target (blue), the brace leg (orange). */
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Line, Polygon, Rect } from 'react-native-svg';

import { Palette, Radius } from '@/constants/palette';
import type { HubState } from '@/lib/hub';

type Props = { state: HubState | null; size: number };

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
        {/* the drone, nose up */}
        <Polygon
          points={`${ox},${oy - 10} ${ox - 8},${oy + 7} ${ox + 8},${oy + 7}`}
          fill={Palette.cream}
          stroke={Palette.cream}
          strokeWidth={1.5}
        />
      </Svg>
      <Text style={styles.caption}>
        {person ? `1 m = ${scale.toFixed(0)} px` : state ? 'no person yet' : 'no link'}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { borderRadius: Radius.panel, overflow: 'hidden', backgroundColor: Palette.ink },
  caption: { position: 'absolute', left: 12, bottom: 8, color: Palette.mute, fontSize: 11 },
});
