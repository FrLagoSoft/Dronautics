/** Laptop address, calibration, and the AMD smoothing status. */
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Pill } from '@/components/ui/buttons';
import { Palette, Radius } from '@/constants/palette';
import { useHub } from '@/lib/hub';
import { useSettings } from '@/lib/settings';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Field({ label, value, onChange, keyboard }: { label: string; value: string; onChange: (v: string) => void; keyboard?: 'numeric' | 'default' }) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        keyboardType={keyboard ?? 'default'}
        autoCapitalize="none"
        autoCorrect={false}
        placeholder="192.168.42.60"
        placeholderTextColor={Palette.mute}
        style={styles.input}
      />
    </View>
  );
}

export default function SettingsScreen() {
  const router = useRouter();
  const { settings, update } = useSettings();
  const { connected, live, state, error, send } = useHub();
  const [host, setHost] = useState(settings.host);
  const [wsPort, setWsPort] = useState(String(settings.wsPort));
  const [videoPort, setVideoPort] = useState(String(settings.videoPort));

  const dirty = host.trim() !== settings.host || Number(wsPort) !== settings.wsPort || Number(videoPort) !== settings.videoPort;
  const save = () =>
    update({
      host: host.trim(),
      wsPort: Number(wsPort) || 8765,
      videoPort: Number(videoPort) || 8766,
    });

  const link = !settings.host ? 'no address set' : live ? 'live' : connected ? 'socket open, no state yet' : (error ?? 'connecting…');
  const cal = state?.calib;
  const amd = state?.interp;

  return (
    <SafeAreaView style={styles.root}>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <View style={styles.titleBlock}>
          <Text style={styles.title}>Settings</Text>
          <View style={styles.rule} />
        </View>

        <Section title="LAPTOP">
          <Text style={styles.help}>
            {'The laptop’s IP on the link to this phone. With USB tethering it’s the address the laptop gets from the phone (on the laptop: ipconfig → the “Ethernet” adapter that appears when you tether).'}
          </Text>
          <Field label="Address" value={host} onChange={setHost} />
          <View style={styles.ports}>
            <Field label="State port" value={wsPort} onChange={setWsPort} keyboard="numeric" />
            <Field label="Video port" value={videoPort} onChange={setVideoPort} keyboard="numeric" />
          </View>
          <Pill label={dirty ? 'Save' : 'Saved'} tone={dirty ? 'ink' : 'sand'} small onPress={save} disabled={!dirty} />
          <Text style={styles.status}>
            link: <Text style={{ color: live ? Palette.ok : Palette.warn }}>{link}</Text>
            {state ? `  ·  ${state.clients} app${state.clients === 1 ? '' : 's'} connected` : ''}
          </Text>
        </Section>

        <Section title="CALIBRATE">
          <Text style={styles.help}>{'Same as the laptop keys a, k, c. Stand in the camera’s view for all three.'}</Text>
          <Pill
            label={`Camera angle  ·  HFOV ${cal ? cal.hfov.toFixed(0) : '-'}°`}
            tone="ghost"
            small
            onPress={() => send({ action: 'cal_angle' })}
            disabled={!live}
          />
          <Text style={styles.hint}>stand centered, press, then turn the drone slowly to one side</Text>
          <Pill
            label={`Distance  ·  ${cal?.k_set ? 'set' : 'not set'}`}
            tone="ghost"
            small
            onPress={() => send({ action: 'cal_dist' })}
            disabled={!live}
          />
          <Text style={styles.hint}>stand exactly 2 m away, whole body in view, then press</Text>
          <Pill
            label={`Align headings  ·  ${cal?.c_set ? 'set' : 'not set'}`}
            tone="ghost"
            small
            onPress={() => send({ action: 'cal_align' })}
            disabled={!live}
          />
          <Text style={styles.hint}>face the drone with the brace on, then press</Text>
          <Pill label="Yaw test  ·  turns right for 1 s" tone="ghost" small onPress={() => send({ action: 'yawtest' })} disabled={!live} />
          <Text style={styles.hint}>if it turns left, flip DRONE_YAW_SIGN in config.py</Text>
        </Section>

        <Section title="AMD SMOOTHING">
          {amd ? (
            <Text style={styles.status}>
              {amd.ok ? 'online' : 'unreachable'} · {amd.model ?? '-'} on {amd.device ?? '-'} [{amd.backend ?? '-'}]
              {'\n'}
              {amd.fps_in ?? '-'} fps in → {amd.fps_out ?? '-'} fps out · {amd.interp_ms ?? '-'} ms per frame
            </Text>
          ) : (
            <Text style={styles.help}>{'Off. Set INTERP_URL in laptop/config.py to the AMD machine’s address.'}</Text>
          )}
        </Section>

        <Pill label="Done" onPress={() => (router.canGoBack() ? router.back() : router.replace('/connect'))} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Palette.clay },
  scroll: { padding: 24, gap: 20, paddingBottom: 48 },
  titleBlock: { alignItems: 'center' },
  title: { color: Palette.cream, fontSize: 28, fontWeight: '300', letterSpacing: 1 },
  rule: { height: 2, width: 110, backgroundColor: Palette.ink, marginTop: 6 },
  section: { backgroundColor: Palette.ink, borderRadius: Radius.panel, padding: 18, gap: 10 },
  sectionTitle: { color: Palette.mute, fontSize: 11, letterSpacing: 2 },
  help: { color: Palette.cream, fontSize: 13, lineHeight: 18, opacity: 0.85 },
  hint: { color: Palette.mute, fontSize: 11, marginTop: -4, marginBottom: 2 },
  field: { gap: 4, flex: 1 },
  fieldLabel: { color: Palette.mute, fontSize: 11, letterSpacing: 1 },
  input: {
    color: Palette.cream,
    backgroundColor: Palette.inkSoft,
    borderRadius: Radius.card,
    paddingVertical: 10,
    paddingHorizontal: 14,
    fontSize: 16,
  },
  ports: { flexDirection: 'row', gap: 10 },
  status: { color: Palette.cream, fontSize: 13, lineHeight: 19 },
});
