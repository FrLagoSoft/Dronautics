/** The simulator: a top-down arena where a virtual drone runs the real leash logic and
 *  pathfinds (A*) around obstacles to stay with you. Your facing comes from the REAL brace when
 *  the laptop link is live; otherwise the on-screen turn buttons. Works with no drone and no laptop. */
import { useRouter } from 'expo-router';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Svg, { Circle, Line, Path, Polygon, Polyline, Rect } from 'react-native-svg';

import { Pill, RoundButton, Toggle } from '@/components/ui/buttons';
import { Palette, Radius } from '@/constants/palette';
import { useHub } from '@/lib/hub';
import { SCENARIOS, SIM, createWorld, framePercent, step, type Input, type Mode, type Scenario, type World } from '@/lib/sim';

const TICK_MS = 50; // 20 Hz, like the laptop's control loop
const RADIUS_STEP = 0.4;

/** A button that acts while held (walk, turn). */
function HoldButton({ label, onDown, onUp, wide }: { label: string; onDown: () => void; onUp: () => void; wide?: boolean }) {
  return (
    <Pressable
      onPressIn={onDown}
      onPressOut={onUp}
      style={({ pressed }) => [styles.hold, wide && styles.holdWide, { backgroundColor: pressed ? Palette.sand : Palette.ink }]}>
      {({ pressed }) => <Text style={[styles.holdText, { color: pressed ? Palette.ink : Palette.cream }]}>{label}</Text>}
    </Pressable>
  );
}

export default function SimScreen() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { state, live } = useHub();
  const braceLive = live && !!state?.brace.ok && state.heading !== null;

  const [scenarioId, setScenarioId] = useState(SCENARIOS[0].id);
  const scenario = useMemo(() => SCENARIOS.find((s) => s.id === scenarioId) ?? SCENARIOS[0], [scenarioId]);
  // worldRef is the live world the loop mutates; `w` is a snapshot of it published each tick for rendering
  const [w, setW] = useState<World>(() => createWorld(scenario));
  const worldRef = useRef<World>(w);
  const inputRef = useRef<Input>({ walk: 0, strafe: 0, turn: 0, braceHeading: null });
  const [running, setRunning] = useState(false);
  const publish = useCallback(() => setW({ ...worldRef.current }), []);

  const reset = useCallback(
    (sc: Scenario) => {
      const prev = worldRef.current;
      worldRef.current = createWorld(sc, prev.radius, prev.mode);
      worldRef.current.orbitDir = prev.orbitDir;
      setRunning(false);
      publish();
    },
    [publish]
  );
  const selectScenario = (id: string) => {
    setScenarioId(id);
    reset(SCENARIOS.find((s) => s.id === id) ?? SCENARIOS[0]);
  };

  // the game loop
  useEffect(() => {
    const t0 = Date.now();
    const id = setInterval(() => {
      const w = worldRef.current;
      w.running = running;
      inputRef.current.braceHeading = braceLive ? (state?.heading ?? null) : null;
      step(w, TICK_MS / 1000, inputRef.current, (Date.now() - t0) / 1000);
      publish();
    }, TICK_MS);
    return () => clearInterval(id);
  }, [running, braceLive, state?.heading, publish]);

  const size = Math.min(width - 32, 420);
  const k = size / w.scenario.size; // px per meter
  const sx = (x: number) => x * k;
  const sy = (y: number) => size - y * k;
  const setInput = (patch: Partial<Input>) => {
    inputRef.current = { ...inputRef.current, ...patch };
  };
  const setMode = (m: Mode) => {
    worldRef.current.mode = m;
    publish();
  };
  const stepRadius = (delta: number) => {
    worldRef.current.radius = Math.min(4, Math.max(1.3, worldRef.current.radius + delta));
    publish();
  };
  const flipOrbit = () => {
    worldRef.current.orbitDir = worldRef.current.orbitDir > 0 ? -1 : 1;
    publish();
  };

  const you = w.person.pos, d = w.drone.pos;
  const headRad = (w.person.heading * Math.PI) / 180;
  const yawRad = (w.drone.yaw * Math.PI) / 180;
  const fov = (SIM.hfov / 2) * (Math.PI / 180);
  const wedgeR = 2.2 * k;
  const wedge = `M ${sx(d.x)} ${sy(d.y)} L ${sx(d.x) + wedgeR * Math.sin(yawRad - fov)} ${sy(d.y) - wedgeR * Math.cos(yawRad - fov)} A ${wedgeR} ${wedgeR} 0 0 1 ${sx(d.x) + wedgeR * Math.sin(yawRad + fov)} ${sy(d.y) - wedgeR * Math.cos(yawRad + fov)} Z`;
  const pct = framePercent(w);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <View>
            <Text style={styles.title}>Simulator</Text>
            <View style={styles.rule} />
          </View>
          <Pressable onPress={() => router.back()}>
            <Text style={styles.back}>back</Text>
          </Pressable>
        </View>

        <View style={styles.stateBox}>
          <Text style={styles.stateMain}>
            {running ? (w.inFrame ? 'IN FRAME' : w.lineOfSight ? 'TURNING TO YOU' : 'BLOCKED: REROUTING') : 'PAUSED'}
          </Text>
          <Text style={styles.stateSub}>
            {w.mode.toUpperCase()} · radius {w.radius.toFixed(1)} m · {braceLive ? 'facing from your brace' : 'facing from the turn buttons'}
          </Text>
        </View>

        {/* arena */}
        <View style={[styles.arena, { width: size, height: size }]}>
          <Svg width={size} height={size}>
            <Rect x={0} y={0} width={size} height={size} fill={Palette.ink} />
            {[...Array(w.scenario.size + 1).keys()].map((m) => (
              <Line key={m} x1={sx(m)} y1={0} x2={sx(m)} y2={size} stroke={Palette.inkSoft} strokeWidth={1} />
            ))}
            {[...Array(w.scenario.size + 1).keys()].map((m) => (
              <Line key={`h${m}`} x1={0} y1={sy(m)} x2={size} y2={sy(m)} stroke={Palette.inkSoft} strokeWidth={1} />
            ))}
            {w.scenario.obstacles.map((o, i) => (
              <Rect key={i} x={sx(o.x)} y={sy(o.y + o.h)} width={o.w * k} height={o.h * k} fill={Palette.clay} stroke={Palette.sand} strokeWidth={1} />
            ))}
            {/* camera wedge and line of sight */}
            <Path d={wedge} fill={w.inFrame ? Palette.ok : Palette.danger} opacity={0.14} />
            <Line x1={sx(d.x)} y1={sy(d.y)} x2={sx(you.x)} y2={sy(you.y)} stroke={w.lineOfSight ? Palette.ok : Palette.danger} strokeWidth={1} strokeDasharray="3 3" />
            {/* leash circle, target, path */}
            <Circle cx={sx(you.x)} cy={sy(you.y)} r={w.radius * k} stroke={Palette.mute} strokeWidth={1} strokeDasharray="4 4" fill="none" />
            {w.path.length ? (
              <Polyline
                points={[d, ...w.path].map((p) => `${sx(p.x)},${sy(p.y)}`).join(' ')}
                stroke={Palette.blue}
                strokeWidth={2}
                strokeDasharray="6 4"
                fill="none"
              />
            ) : null}
            <Circle cx={sx(w.target.x)} cy={sy(w.target.y)} r={6} stroke={Palette.blue} strokeWidth={2} fill="none" />
            {/* you */}
            <Line
              x1={sx(you.x)} y1={sy(you.y)}
              x2={sx(you.x) + 0.8 * k * Math.sin(headRad)} y2={sy(you.y) - 0.8 * k * Math.cos(headRad)}
              stroke={Palette.orange} strokeWidth={3} strokeLinecap="round"
            />
            <Circle cx={sx(you.x)} cy={sy(you.y)} r={7} fill={Palette.cream} />
            {/* the drone, nose along its yaw */}
            <Polygon
              points={[
                [0, -11], [-7, 7], [7, 7],
              ]
                .map(([px, py]) => {
                  const rx = px * Math.cos(yawRad) - py * Math.sin(yawRad);
                  const ry = px * Math.sin(yawRad) + py * Math.cos(yawRad);
                  return `${sx(d.x) + rx},${sy(d.y) + ry}`;
                })
                .join(' ')}
              fill={w.inFrame ? Palette.ok : Palette.sand}
            />
          </Svg>
        </View>

        {/* score */}
        <View style={styles.scoreRow}>
          <View style={styles.scoreBox}><Text style={styles.scoreNum}>{pct}%</Text><Text style={styles.scoreLabel}>in frame</Text></View>
          <View style={styles.scoreBox}><Text style={styles.scoreNum}>{w.score.closeCalls}</Text><Text style={styles.scoreLabel}>close calls</Text></View>
          <View style={styles.scoreBox}><Text style={styles.scoreNum}>{w.score.pathMeters.toFixed(0)} m</Text><Text style={styles.scoreLabel}>flown</Text></View>
          <View style={styles.scoreBox}><Text style={styles.scoreNum}>{w.score.seconds.toFixed(0)} s</Text><Text style={styles.scoreLabel}>time</Text></View>
        </View>

        {/* run controls */}
        <View style={styles.flightRow}>
          <Pill label={running ? 'PAUSE' : 'START'} tone={running ? 'sand' : 'ink'} onPress={() => setRunning((r) => !r)} style={styles.flex} />
          <Pill label="RESET" tone="ghost" onPress={() => reset(scenario)} style={styles.flex} />
        </View>

        {/* walking: hold to move */}
        <Text style={styles.sectionTitle}>YOU</Text>
        <View style={styles.padRow}>
          <HoldButton label="↶ turn" onDown={() => setInput({ turn: -1 })} onUp={() => setInput({ turn: 0 })} />
          <HoldButton label="▲ walk" onDown={() => setInput({ walk: 1 })} onUp={() => setInput({ walk: 0 })} wide />
          <HoldButton label="turn ↷" onDown={() => setInput({ turn: 1 })} onUp={() => setInput({ turn: 0 })} />
        </View>
        <View style={styles.padRow}>
          <HoldButton label="◀ step" onDown={() => setInput({ strafe: -1 })} onUp={() => setInput({ strafe: 0 })} />
          <HoldButton label="▼ back" onDown={() => setInput({ walk: -1 })} onUp={() => setInput({ walk: 0 })} wide />
          <HoldButton label="step ▶" onDown={() => setInput({ strafe: 1 })} onUp={() => setInput({ strafe: 0 })} />
        </View>
        {braceLive ? <Text style={styles.hint}>turn buttons are off: your real brace sets where you face</Text> : null}

        {/* leash settings */}
        <Text style={styles.sectionTitle}>LEASH</Text>
        <View style={styles.toggles}>
          <Toggle label="FOLLOW" hint="keep the radius, line of sight" on={w.mode === 'follow'} onPress={() => setMode('follow')} />
          <Toggle label="FRONT" hint="stay in front of you" on={w.mode === 'front'} onPress={() => setMode('front')} />
          <Toggle label="ORBIT" hint={w.orbitDir > 0 ? 'circling right' : 'circling left'} on={w.mode === 'orbit'} onPress={() => setMode('orbit')} />
        </View>
        <View style={styles.radiusRow}>
          <RoundButton label="IN" onPress={() => stepRadius(-RADIUS_STEP)} />
          <Text style={styles.radiusText}>{w.radius.toFixed(1)} m</Text>
          <RoundButton label="OUT" onPress={() => stepRadius(RADIUS_STEP)} />
          <Pill label="FLIP ORBIT" tone="ghost" small onPress={flipOrbit} />
        </View>

        {/* scenarios */}
        <Text style={styles.sectionTitle}>SCENARIO</Text>
        <View style={styles.scenarios}>
          {SCENARIOS.map((s) => (
            <Pill key={s.id} label={s.name.toUpperCase()} tone={s.id === scenarioId ? 'ink' : 'ghost'} small onPress={() => selectScenario(s.id)} />
          ))}
        </View>
        <Text style={styles.hint}>{scenario.blurb}</Text>

        <Text style={styles.legendText}>
          {'cream = you · orange = where you face · blue ring = leash target · blue dashes = the drone’s planned path'}
          {'\n'}green wedge = the camera sees you · red = line of sight blocked, re-routing
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Palette.peach },
  scroll: { paddingHorizontal: 16, paddingBottom: 40, gap: 12, alignItems: 'stretch' },
  header: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: 8 },
  title: { color: Palette.ink, fontSize: 30, fontWeight: '300', letterSpacing: 1 },
  rule: { height: 2, backgroundColor: Palette.ink, marginTop: 4 },
  back: { color: Palette.ink, fontSize: 14, textDecorationLine: 'underline', paddingBottom: 8 },
  stateBox: { backgroundColor: Palette.ink, borderRadius: Radius.card, paddingVertical: 10, paddingHorizontal: 14 },
  stateMain: { color: Palette.cream, fontSize: 18, fontWeight: '600', letterSpacing: 0.5 },
  stateSub: { color: Palette.mute, fontSize: 12, marginTop: 2 },
  arena: { alignSelf: 'center', borderRadius: Radius.card, overflow: 'hidden' },
  scoreRow: { flexDirection: 'row', gap: 8 },
  scoreBox: { flex: 1, backgroundColor: Palette.ink, borderRadius: Radius.card, paddingVertical: 8, alignItems: 'center' },
  scoreNum: { color: Palette.cream, fontSize: 18, fontWeight: '600', fontVariant: ['tabular-nums'] },
  scoreLabel: { color: Palette.mute, fontSize: 10, letterSpacing: 1 },
  flightRow: { flexDirection: 'row', gap: 10 },
  flex: { flex: 1 },
  sectionTitle: { color: Palette.inkSoft, fontSize: 11, letterSpacing: 2, marginTop: 4 },
  padRow: { flexDirection: 'row', gap: 8 },
  hold: { flex: 1, paddingVertical: 14, borderRadius: Radius.card, alignItems: 'center', justifyContent: 'center' },
  holdWide: { flex: 1.6 },
  holdText: { fontSize: 15, fontWeight: '600', letterSpacing: 0.5 },
  toggles: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  radiusRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  radiusText: { color: Palette.ink, fontSize: 16, fontWeight: '600', minWidth: 52, textAlign: 'center' },
  scenarios: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  hint: { color: Palette.inkSoft, fontSize: 12 },
  legendText: { color: Palette.inkSoft, fontSize: 11, lineHeight: 16, marginTop: 4 },
});
