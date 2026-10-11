/** The control room: radius IN/OUT, the map, the camera, flight buttons, the feed. */
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { LeashMap } from '@/components/leash-map';
import { Pill, RoundButton, Toggle } from '@/components/ui/buttons';
import { VideoView } from '@/components/video-view';
import { Palette, Radius } from '@/constants/palette';
import { useHub } from '@/lib/hub';
import { useSettings, videoBase } from '@/lib/settings';

const RADIUS_STEP = 0.4; // same as RADIUS_STEP in laptop/config.py
const HEIGHT_STEP = 10; // cm, same as HEIGHT_STEP_CM in laptop/config.py

/** The drone's current command in words: what it's doing right now. */
function describeMovement(cmd: { lr: number; fb: number; ud: number; yaw: number } | undefined) {
  if (!cmd) return null;
  const parts: string[] = [];
  const min = 3;
  if (cmd.fb >= min) parts.push('↑ moving closer');
  else if (cmd.fb <= -min) parts.push('↓ backing away');
  if (cmd.lr >= min) parts.push('→ sliding right');
  else if (cmd.lr <= -min) parts.push('← sliding left');
  if (cmd.yaw >= min) parts.push('↻ turning right');
  else if (cmd.yaw <= -min) parts.push('↺ turning left');
  if (cmd.ud >= min) parts.push('▲ climbing');
  else if (cmd.ud <= -min) parts.push('▼ descending');
  return parts.length ? parts.join('   ') : '● holding still';
}

function Legend({ color, label, ring }: { color: string; label: string; ring?: boolean }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.legendDot, ring ? { borderColor: color, borderWidth: 1.5 } : { backgroundColor: color }]} />
      <Text style={styles.legendText}>{label}</Text>
    </View>
  );
}

/** One calibration step: the laptop key letter, what it sets, and whether it's done. */
function CalTile({
  letter,
  label,
  status,
  done,
  onPress,
  disabled,
}: {
  letter: string;
  label: string;
  status: string;
  done: boolean | null;
  onPress: () => void;
  disabled: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.calTile,
        done ? styles.calTileDone : null,
        { opacity: disabled ? 0.4 : pressed ? 0.7 : 1 },
      ]}>
      <Text style={[styles.calLetter, done ? styles.calInkText : null]}>{letter}</Text>
      <Text style={[styles.calLabel, done ? styles.calInkText : null]}>{label}</Text>
      <Text style={[styles.calStatus, done ? styles.calInkSoft : null]}>{status}</Text>
    </Pressable>
  );
}

function Chip({ label, good }: { label: string; good: boolean | null }) {
  const color = good === null ? Palette.mute : good ? Palette.ok : Palette.danger;
  return (
    <View style={styles.chip}>
      <View style={[styles.chipDot, { backgroundColor: color }]} />
      <Text style={styles.chipText}>{label}</Text>
    </View>
  );
}

export default function ControlScreen() {
  const router = useRouter();
  const { width, height } = useWindowDimensions();
  const { settings } = useSettings();
  const { state, live, events, send } = useHub();
  const [smoothed, setSmoothed] = useState(false);
  const [mapOpen, setMapOpen] = useState(false);

  // the newest calibration message from the laptop (success or what to fix), shown under the buttons
  const calNote = events.find((e) => /calibrat|Distance constants|Headings aligned|Can't|DRONE_YAW_SIGN/i.test(e.text))?.text;

  const base = videoBase(settings);
  const amd = state?.interp && state.interp.ok ? state.interp : null;
  const videoUri = smoothed && amd ? amd.stream : base ? `${base}/stream` : null;

  const s = state;
  const flying = s?.flying ?? false;
  const radius = s?.radius ?? null;
  const gap = 16;
  const mapSize = Math.min(220, width - 32 - 76 - gap);

  const battery = s?.battery ?? null;
  const batteryGood = battery === null ? null : battery > 30;

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {/* header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.title}>Dronautics</Text>
            <View style={styles.rule} />
          </View>
          <View style={styles.headerRight}>
            <Text style={styles.battery}>{battery === null ? '--' : `${battery}%`}</Text>
            <View style={[styles.liveDot, { backgroundColor: live ? Palette.ok : Palette.danger }]} />
          </View>
        </View>

        {/* state line */}
        <View style={styles.stateBox}>
          <Text style={styles.stateMain} numberOfLines={1}>
            {live ? (s?.state ?? '-') : 'NO LINK TO LAPTOP'}
          </Text>
          <Text style={styles.stateSub}>
            {live && s
              ? `${s.mode}${s.gentle ? ' · gentle' : ' · full'}${s.indoor === undefined ? '' : s.indoor ? ' · indoor' : ' · outdoor'}${s.manual ? ' · GLOVE' : ''}${s.dry_run ? ' · DRY RUN' : ''}`
              : 'check Settings'}
          </Text>
          {live && s && (s.flying || s.dry_run) ? (
            <Text style={styles.movement} numberOfLines={1}>
              {describeMovement(s.cmd)}
            </Text>
          ) : null}
        </View>

        {/* radius + map */}
        <View style={[styles.row, { gap }]}>
          <View style={styles.radiusCol}>
            <RoundButton label="IN" onPress={() => send({ action: 'radius_step', value: -RADIUS_STEP })} disabled={!live} />
            <Text style={styles.radiusText}>{radius === null ? '-' : `${radius.toFixed(1)} m`}</Text>
            <RoundButton label="OUT" onPress={() => send({ action: 'radius_step', value: RADIUS_STEP })} disabled={!live} />
          </View>
          <Pressable onPress={() => setMapOpen(true)} style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}>
            <LeashMap state={live ? s : null} size={mapSize} />
            <Text style={styles.mapHint}>tap to expand</Text>
          </Pressable>
        </View>

        {/* altitude hold */}
        <View style={styles.heightRow}>
          <View>
            <Text style={styles.heightLabel}>HEIGHT</Text>
            <Text style={styles.heightValue}>
              {s?.height != null ? `${s.height} cm` : '-'}
              <Text style={styles.heightTarget}>
                {s?.target_height != null ? `  →  holding ${s.target_height} cm` : ''}
              </Text>
            </Text>
          </View>
          <View style={styles.heightButtons}>
            <RoundButton label="▼" size={46} onPress={() => send({ action: 'height_step', value: -HEIGHT_STEP })} disabled={!live || s?.target_height === undefined} />
            <RoundButton label="▲" size={46} onPress={() => send({ action: 'height_step', value: HEIGHT_STEP })} disabled={!live || s?.target_height === undefined} />
          </View>
        </View>

        {/* the big map */}
        <Modal visible={mapOpen} transparent animationType="fade" onRequestClose={() => setMapOpen(false)}>
          <Pressable style={styles.mapBackdrop} onPress={() => setMapOpen(false)}>
            <Text style={styles.mapTitle}>LEASH MAP</Text>
            <LeashMap state={live ? s : null} size={Math.min(width, height) - 32} />
            <View style={styles.legend}>
              <Legend color={Palette.cream} label="you" />
              <Legend color={Palette.mute} label="leash" ring />
              <Legend color={Palette.blue} label="target" ring />
              <Legend color={Palette.orange} label="brace leg" />
              <Legend color={Palette.ok} label="drone moving" />
            </View>
            <Text style={styles.mapReadout}>
              {s
                ? `d ${s.d === null ? '-' : s.d.toFixed(2)} m · bearing ${s.bearing === null ? '-' : `${s.bearing.toFixed(0)}°`} · radius ${s.radius.toFixed(1)} m`
                : 'no link'}
            </Text>
            <View style={styles.mapButtons}>
              <RoundButton label="IN" tone="sand" onPress={() => send({ action: 'radius_step', value: -RADIUS_STEP })} disabled={!live} />
              <RoundButton label="OUT" tone="sand" onPress={() => send({ action: 'radius_step', value: RADIUS_STEP })} disabled={!live} />
            </View>
            <Text style={styles.mapClose}>tap anywhere to close</Text>
          </Pressable>
        </Modal>

        {/* camera */}
        <View style={styles.videoWrap}>
          <View style={[styles.bracket, styles.bracketTR]} />
          <View style={[styles.bracket, styles.bracketBL]} />
          <View style={[styles.video, { height: Math.round((width - 32) * 0.62) }]}>
            <VideoView uri={live ? videoUri : null} label={live ? 'no video' : 'no link'} />
          </View>
          <View style={styles.videoBar}>
            <Text style={styles.videoLabel}>
              {smoothed && amd ? `AMD · ${amd.fps_out ?? '-'} fps` : 'RAW · laptop'}
            </Text>
            <Pressable onPress={() => setSmoothed((v) => !v)} disabled={!amd} style={{ opacity: amd ? 1 : 0.4 }}>
              <Text style={styles.videoSwitch}>{amd ? (smoothed ? 'show raw' : 'show AMD smoothed') : 'AMD offline'}</Text>
            </Pressable>
          </View>
        </View>

        {/* flight */}
        <View style={styles.flightRow}>
          <Pill
            label={flying ? 'LAND' : 'TAKE OFF'}
            tone={flying ? 'sand' : 'ink'}
            onPress={() => send({ action: flying ? 'land' : 'takeoff' })}
            disabled={!live}
            style={styles.flex}
          />
          <Pill label="RE-LOCK" tone="ghost" onPress={() => send({ action: 'relock' })} disabled={!live} style={styles.flex} />
        </View>

        <View style={styles.toggles}>
          <Toggle
            label="FOLLOW"
            hint={s?.following ? 'moving with you' : 'hover only'}
            on={s?.following ?? false}
            onPress={() => send({ action: 'follow', on: !(s?.following ?? false) })}
            disabled={!live}
          />
          <Toggle
            label="ORBIT"
            hint={s?.orbiting ? (s.orbit_dir > 0 ? 'circling right' : 'circling left') : 'off'}
            on={s?.orbiting ?? false}
            onPress={() => send({ action: 'orbit', on: !(s?.orbiting ?? false) })}
            disabled={!live}
          />
          <Toggle
            label="WATCH"
            hint="turn to face you"
            on={s?.watch ?? false}
            onPress={() => send({ action: 'watch', on: !(s?.watch ?? false) })}
            disabled={!live}
          />
          <Toggle
            label="GENTLE"
            hint="half speed"
            on={s?.gentle ?? false}
            onPress={() => send({ action: 'gentle', on: !(s?.gentle ?? false) })}
            disabled={!live}
          />
          <Toggle
            label={s?.indoor === false ? 'OUTDOOR' : 'INDOOR'}
            hint={s?.indoor === false ? 'quick to search, predicts your path' : 'patient turning, small search'}
            on={s?.indoor ?? true}
            onPress={() => send({ action: 'indoor', on: !(s?.indoor ?? true) })}
            disabled={!live || s?.indoor === undefined}
          />
        </View>
        <Pill
          label={`FLIP ORBIT DIRECTION  (${(s?.orbit_dir ?? 1) > 0 ? 'right' : 'left'})`}
          tone="ghost"
          small
          onPress={() => send({ action: 'orbit_dir', value: (s?.orbit_dir ?? 1) > 0 ? -1 : 1 })}
          disabled={!live}
        />

        {/* status chips */}
        <View style={styles.chips}>
          <Chip label={`brace ${s?.brace.ok ? 'OK' : 'lost'}${s?.brace.acc != null ? ` · acc ${s.brace.acc}` : ''}`} good={s ? s.brace.ok : null} />
          <Chip label={`glove ${s?.glove.ok ? (s.glove.clutch ? 'CLUTCH' : 'OK') : '-'}`} good={s ? s.glove.ok : null} />
          <Chip
            label={
              s?.gps
                ? `GPS fix ${s.gps.fix} · ${s.gps.sats} sats` +
                  (s.gps.walking ? ` · ${s.gps.walking.toFixed(1)} m/s${s.gps.used ? ' · STEERING' : ''}` : '')
                : 'GPS -'
            }
            good={s?.gps ? s.gps.fix >= 2 : null}
          />
          <Chip
            label={`lock ${s?.lock != null ? `#${s.lock}` : 'none'} · ${s?.people ?? 0} in view`}
            good={s ? s.lock != null : null}
          />
          <Chip label={batteryGood === null ? 'battery -' : `battery ${battery}%`} good={batteryGood} />
          <Chip
            label={`cal ${s?.calib.k_set ? 'K' : 'k?'} ${s?.calib.c_set ? 'C' : 'c?'} HFOV ${s ? s.calib.hfov.toFixed(0) : '-'}`}
            good={s ? s.calib.k_set && s.calib.c_set : null}
          />
        </View>

        {/* telemetry */}
        {s ? (
          <Text style={styles.telemetry}>
            d {s.d === null ? '-' : s.d.toFixed(2)} m · bearing {s.bearing === null ? '-' : `${s.bearing > 0 ? '+' : ''}${s.bearing.toFixed(0)}°`}
            {' · '}brace {s.heading === null ? '-' : `${s.heading.toFixed(0)}°`}
            {'\n'}cmd lr {s.cmd.lr} fb {s.cmd.fb} ud {s.cmd.ud} yaw {s.cmd.yaw}
          </Text>
        ) : null}

        {/* feed */}
        <View style={styles.feed}>
          <Text style={styles.feedTitle}>FEED</Text>
          {events.length === 0 ? <Text style={styles.feedLine}>nothing yet</Text> : null}
          {events.slice(0, 8).map((e) => (
            <Text key={e.id} style={styles.feedLine} numberOfLines={2}>
              <Text style={styles.feedTime}>{new Date(e.t * 1000).toLocaleTimeString([], { hour12: false })} </Text>
              {e.text}
            </Text>
          ))}
        </View>

        {/* calibration: the laptop keys a / k / c / y, one tap each */}
        <View style={styles.calCard}>
          <View style={styles.calHeader}>
            <Text style={styles.calTitle}>CALIBRATE</Text>
            <Pressable onPress={() => router.push('/settings')} hitSlop={10}>
              <Text style={styles.calHelp}>how ›</Text>
            </Pressable>
          </View>
          <View style={styles.calRow}>
            <CalTile
              letter="K"
              label="distance"
              status={s?.calib.k_set ? 'set' : 'stand 2 m'}
              done={s ? s.calib.k_set : null}
              onPress={() => send({ action: 'cal_dist' })}
              disabled={!live}
            />
            <CalTile
              letter="C"
              label="headings"
              status={s?.calib.c_set ? 'set' : 'face drone'}
              done={s ? s.calib.c_set : null}
              onPress={() => send({ action: 'cal_align' })}
              disabled={!live}
            />
            <CalTile
              letter="A"
              label="angle"
              status={s ? `${s.calib.hfov.toFixed(0)}°` : '-'}
              done={null}
              onPress={() => send({ action: 'cal_angle' })}
              disabled={!live}
            />
            <CalTile
              letter="Y"
              label="yaw test"
              status="turns right"
              done={null}
              onPress={() => send({ action: 'yawtest' })}
              disabled={!live}
            />
          </View>
          {calNote ? <Text style={styles.calNote}>{calNote}</Text> : null}
        </View>

        <Pill label="SIMULATOR" tone="ghost" onPress={() => router.push('/sim')} />

        {/* emergency: hold, so a stray tap can't drop the drone */}
        <Pill
          label="HOLD · EMERGENCY STOP"
          tone="danger"
          onLongPress={() => send({ action: 'emergency' })}
          delayLongPress={700}
          disabled={!live}
          style={styles.emergency}
        />
        <Text style={styles.emergencyHint}>cuts the motors immediately, the drone falls</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Palette.peach },
  scroll: { paddingHorizontal: 16, paddingBottom: 40, gap: 14 },
  header: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: 8 },
  title: { color: Palette.ink, fontSize: 30, fontWeight: '300', letterSpacing: 1 },
  rule: { height: 2, backgroundColor: Palette.ink, marginTop: 4 },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingBottom: 6 },
  battery: { color: Palette.ink, fontSize: 16, fontWeight: '600' },
  liveDot: { width: 12, height: 12, borderRadius: 6 },
  stateBox: { backgroundColor: Palette.ink, borderRadius: Radius.card, paddingVertical: 10, paddingHorizontal: 14 },
  stateMain: { color: Palette.cream, fontSize: 18, fontWeight: '600', letterSpacing: 0.5 },
  stateSub: { color: Palette.mute, fontSize: 12, marginTop: 2 },
  movement: { color: Palette.ok, fontSize: 15, fontWeight: '600', marginTop: 6, letterSpacing: 0.3 },
  row: { flexDirection: 'row', alignItems: 'center' },
  radiusCol: { alignItems: 'center', gap: 10, width: 76 },
  radiusText: { color: Palette.ink, fontSize: 15, fontWeight: '600' },
  heightRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: Palette.ink,
    borderRadius: Radius.card,
    paddingVertical: 10,
    paddingHorizontal: 14,
  },
  heightLabel: { color: Palette.mute, fontSize: 11, letterSpacing: 2 },
  heightValue: { color: Palette.cream, fontSize: 18, fontWeight: '600', fontVariant: ['tabular-nums'], marginTop: 2 },
  heightTarget: { color: Palette.mute, fontSize: 13, fontWeight: '400' },
  heightButtons: { flexDirection: 'row', gap: 10 },
  mapHint: { position: 'absolute', right: 12, top: 8, color: Palette.mute, fontSize: 10, letterSpacing: 1 },
  mapBackdrop: { flex: 1, backgroundColor: 'rgba(20,14,10,0.94)', alignItems: 'center', justifyContent: 'center', gap: 16 },
  mapTitle: { color: Palette.cream, fontSize: 13, letterSpacing: 3 },
  legend: { flexDirection: 'row', gap: 16, flexWrap: 'wrap', justifyContent: 'center' },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  legendDot: { width: 10, height: 10, borderRadius: 5 },
  legendText: { color: Palette.cream, fontSize: 12 },
  mapReadout: { color: Palette.mute, fontSize: 13, fontVariant: ['tabular-nums'] },
  mapButtons: { flexDirection: 'row', gap: 24 },
  mapClose: { color: Palette.mute, fontSize: 11, letterSpacing: 1, marginTop: 8 },
  flex: { flex: 1 },
  videoWrap: { position: 'relative', paddingVertical: 10, paddingHorizontal: 10 },
  video: { borderRadius: Radius.panel, overflow: 'hidden', backgroundColor: '#000' },
  bracket: { position: 'absolute', width: 44, height: 44, borderColor: Palette.ink },
  bracketTR: { top: 0, right: 0, borderTopWidth: 3, borderRightWidth: 3 },
  bracketBL: { bottom: 0, left: 0, borderBottomWidth: 3, borderLeftWidth: 3 },
  videoBar: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 8, paddingTop: 8 },
  videoLabel: { color: Palette.ink, fontSize: 12, letterSpacing: 1 },
  videoSwitch: { color: Palette.ink, fontSize: 12, textDecorationLine: 'underline' },
  flightRow: { flexDirection: 'row', gap: 10 },
  toggles: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: Palette.ink,
    borderRadius: Radius.pill,
    paddingVertical: 6,
    paddingHorizontal: 10,
  },
  chipDot: { width: 8, height: 8, borderRadius: 4 },
  chipText: { color: Palette.cream, fontSize: 12 },
  telemetry: { color: Palette.inkSoft, fontSize: 12, fontVariant: ['tabular-nums'], lineHeight: 18 },
  calCard: { backgroundColor: Palette.ink, borderRadius: Radius.panel, padding: 14, gap: 10 },
  calHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  calTitle: { color: Palette.mute, fontSize: 11, letterSpacing: 2 },
  calHelp: { color: Palette.sand, fontSize: 12 },
  calRow: { flexDirection: 'row', gap: 8 },
  calTile: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 10,
    borderRadius: Radius.card,
    borderWidth: 1.5,
    borderColor: Palette.inkSoft,
    backgroundColor: Palette.inkSoft,
  },
  calTileDone: { backgroundColor: Palette.sand, borderColor: Palette.sand },
  calLetter: { color: Palette.cream, fontSize: 22, fontWeight: '300' },
  calLabel: { color: Palette.cream, fontSize: 11, marginTop: 2 },
  calStatus: { color: Palette.mute, fontSize: 10, marginTop: 2 },
  calInkText: { color: Palette.ink },
  calInkSoft: { color: Palette.inkSoft },
  calNote: { color: Palette.cream, fontSize: 12, opacity: 0.85 },
  feed: { backgroundColor: Palette.ink, borderRadius: Radius.card, padding: 12, gap: 4 },
  feedTitle: { color: Palette.mute, fontSize: 11, letterSpacing: 2, marginBottom: 4 },
  feedLine: { color: Palette.cream, fontSize: 13 },
  feedTime: { color: Palette.mute, fontVariant: ['tabular-nums'] },
  emergency: { marginTop: 6 },
  emergencyHint: { color: Palette.inkSoft, fontSize: 11, textAlign: 'center', marginTop: -6 },
});
