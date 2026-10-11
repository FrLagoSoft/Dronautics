/** "No Drone Found" / "Drone Found!": waits for the laptop's hub, then lets you in. */
import { useRouter } from 'expo-router';
import { useEffect } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Pill } from '@/components/ui/buttons';
import { Palette } from '@/constants/palette';
import { useHub } from '@/lib/hub';
import { useSettings } from '@/lib/settings';

const CIRCLE = 220;

/** A thin ring that spreads out from the circle's edge and fades, like a drop hitting water. */
function Ring({ delay }: { delay: number }) {
  const p = useSharedValue(0);
  useEffect(() => {
    const id = setTimeout(() => {
      p.value = withRepeat(withTiming(1, { duration: 2400, easing: Easing.out(Easing.cubic) }), -1, false);
    }, delay);
    return () => clearTimeout(id);
  }, [delay, p]);
  const style = useAnimatedStyle(() => ({
    transform: [{ scale: 1 + 0.75 * p.value }],
    opacity: 0.6 * (1 - p.value) * (1 - p.value),
    borderWidth: 2.5 - 1.5 * p.value,
  }));
  return <Animated.View pointerEvents="none" style={[styles.ring, style]} />;
}

export default function ConnectScreen() {
  const router = useRouter();
  const { settings } = useSettings();
  const { live, connected, state, error, searching } = useHub();
  const found = live && state !== null;

  // the "plop": a quick swell and settle the moment the drone appears
  const plop = useSharedValue(1);
  useEffect(() => {
    if (found) plop.value = withSequence(withTiming(1.08, { duration: 140 }), withSpring(1, { damping: 9, stiffness: 160 }));
  }, [found, plop]);
  const plopStyle = useAnimatedStyle(() => ({ transform: [{ scale: plop.value }] }));

  let caption: string;
  if (searching && !connected) caption = 'searching for the laptop on the USB hotspot…';
  else if (!settings.host) caption = 'Plug the iPhone into the laptop with Personal Hotspot on';
  else if (found) caption = state.dry_run ? 'laptop in DRY RUN (webcam)' : 'Tello linked through the laptop';
  else if (connected) caption = 'laptop linked, waiting for the drone';
  else caption = error ?? `looking for ${settings.host}`;

  return (
    <SafeAreaView style={styles.root}>
      <View style={styles.titleBlock}>
        <Text style={styles.title}>Dronautics</Text>
        <Text style={styles.tagline}>Revolutionizing control</Text>
        <View style={styles.rule} />
      </View>

      <View style={styles.center}>
        <View style={styles.circleWrap}>
          {found ? (
            <>
              <Ring delay={0} />
              <Ring delay={800} />
              <Ring delay={1600} />
            </>
          ) : null}
          <Animated.View style={plopStyle}>
            <Pressable
              onPress={() => router.replace('/control')}
              disabled={!found}
              style={({ pressed }) => [
                styles.circle,
                found ? styles.circleFound : styles.circleIdle,
                pressed && found && { transform: [{ scale: 0.97 }] },
              ]}>
              <Text style={[styles.circleText, { color: found ? Palette.ink : Palette.cream }]}>
                {found ? 'Drone Found!' : 'No Drone Found'}
              </Text>
              {found ? <Text style={styles.circleHint}>tap to take control</Text> : null}
            </Pressable>
          </Animated.View>
        </View>
        <Text style={styles.caption}>{caption}</Text>
      </View>

      <View style={styles.bottom}>
        <Pill label="Simulator  ·  no drone needed" tone="ghost" onPress={() => router.push('/sim')} />
        <Pill label="Settings" onPress={() => router.push('/settings')} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Palette.clay, alignItems: 'center' },
  titleBlock: { alignItems: 'center', marginTop: 40 },
  title: { color: Palette.cream, fontSize: 30, fontWeight: '300', letterSpacing: 1 },
  tagline: { color: Palette.cream, fontSize: 12, opacity: 0.8, marginTop: 2 },
  rule: { height: 2, width: 130, backgroundColor: Palette.ink, marginTop: 10 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 24 },
  circleWrap: { width: CIRCLE, height: CIRCLE, alignItems: 'center', justifyContent: 'center' },
  ring: {
    position: 'absolute',
    width: CIRCLE,
    height: CIRCLE,
    borderRadius: CIRCLE / 2,
    borderColor: Palette.sand,
  },
  circle: {
    width: CIRCLE,
    height: CIRCLE,
    borderRadius: CIRCLE / 2,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  circleIdle: { backgroundColor: Palette.ink },
  circleFound: { backgroundColor: Palette.sand },
  circleText: { fontSize: 20, fontWeight: '400', letterSpacing: 0.5 },
  circleHint: { fontSize: 11, color: Palette.inkSoft, letterSpacing: 1 },
  caption: { color: Palette.cream, fontSize: 13, opacity: 0.85, paddingHorizontal: 32, textAlign: 'center' },
  bottom: { alignSelf: 'stretch', paddingHorizontal: 32, paddingBottom: 24, gap: 10 },
});
