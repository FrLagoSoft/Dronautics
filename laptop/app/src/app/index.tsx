/** Splash: the title, the bobbing drone, "Loading". Moves on by itself. */
import { useRouter } from 'expo-router';
import { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, { Easing, useAnimatedStyle, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { DroneGlyph } from '@/components/drone-glyph';
import { Palette } from '@/constants/palette';
import { useSettings } from '@/lib/settings';

const SPLASH_MS = 2200;

export default function SplashScreen() {
  const router = useRouter();
  const { loaded } = useSettings();

  useEffect(() => {
    if (!loaded) return;
    const id = setTimeout(() => router.replace('/connect'), SPLASH_MS);
    return () => clearTimeout(id);
  }, [loaded, router]);

  const pulse = useSharedValue(0.4);
  useEffect(() => {
    pulse.value = withRepeat(withTiming(1, { duration: 700, easing: Easing.inOut(Easing.quad) }), -1, true);
  }, [pulse]);
  const loadingStyle = useAnimatedStyle(() => ({ opacity: pulse.value }));

  return (
    <SafeAreaView style={styles.root}>
      <View style={styles.titleBlock}>
        <Text style={styles.title}>Dronautics</Text>
        <View style={styles.rule} />
      </View>
      <View style={styles.center}>
        <DroneGlyph size={150} />
        <View style={styles.ground} />
        <Animated.Text style={[styles.loading, loadingStyle]}>Loading</Animated.Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Palette.bark, alignItems: 'center' },
  titleBlock: { alignItems: 'center', marginTop: 90 },
  title: { color: Palette.cream, fontSize: 34, fontWeight: '300', letterSpacing: 1 },
  rule: { height: 2, width: 150, backgroundColor: Palette.ink, marginTop: 6 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 18 },
  ground: { height: 3, width: 170, backgroundColor: Palette.ink, borderRadius: 2, marginTop: -14 },
  loading: { color: Palette.cream, fontSize: 26, fontWeight: '300', letterSpacing: 1 },
});
