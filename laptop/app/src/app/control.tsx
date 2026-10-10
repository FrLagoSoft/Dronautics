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

function Legend({ color, label, ring }: { color: string; label: string; ring?: boolean }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.legendDot, ring ? { borderColor: color, borderWidth: 1.5 } : { backgroundColor: color }]} />
      <Text style={styles.legendText}>{label}</Text>
    </View>
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
              ? `${s.mode}${s.gentle ? ' · gentle' : ' · full'}${s.manual ? ' · GLOVE' : ''}${s.dry_run ? ' · DRY RUN' : ''}`
              : 'check Settings'}
          </Text>
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
            label={s?.gps ? `GPS fix ${s.gps.fix} · ${s.gps.sats} sats` : 'GPS -'}
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

        <Pill label="CALIBRATE" onPress={() => router.push('/settings')} />

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
  row: { flexDirection: 'row', alignItems: 'center' },
  radiusCol: { alignItems: 'center', gap: 10, width: 76 },
  radiusText: { color: Palette.ink, fontSize: 15, fontWeight: '600' },
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
  feed: { backgroundColor: Palette.ink, borderRadius: Radius.card, padding: 12, gap: 4 },
  feedTitle: { color: Palette.mute, fontSize: 11, letterSpacing: 2, marginBottom: 4 },
  feedLine: { color: Palette.cream, fontSize: 13 },
  feedTime: { color: Palette.mute, fontVariant: ['tabular-nums'] },
  emergency: { marginTop: 6 },
  emergencyHint: { color: Palette.inkSoft, fontSize: 11, textAlign: 'center', marginTop: -6 },
});
