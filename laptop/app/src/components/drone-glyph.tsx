/** The splash drone, front view: two motor pods with spinning props on a crossbar, a body with a camera,
 *  two landing legs, and a ground shadow. It hovers (bobs + a slight tilt) while the props spin. */
import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { Easing, useAnimatedStyle, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated';

import { Palette } from '@/constants/palette';

type Props = { size?: number; animate?: boolean; legColor?: string; bodyColor?: string };

const W = 160; // design width; everything scales from here
const H = 175;

export function DroneGlyph({ size = 160, animate = true, legColor = Palette.cream, bodyColor = Palette.ink }: Props) {
  const bob = useSharedValue(0); // 0 = low, 1 = high
  const spin = useSharedValue(0); // one prop revolution per cycle

  useEffect(() => {
    if (!animate) return;
    bob.value = withRepeat(withTiming(1, { duration: 1500, easing: Easing.inOut(Easing.sin) }), -1, true);
    spin.value = withRepeat(withTiming(1, { duration: 170, easing: Easing.linear }), -1, false);
  }, [animate, bob, spin]);

  const u = size / W;
  const hover = useAnimatedStyle(() => ({
    transform: [{ translateY: -14 * u * bob.value }, { rotate: `${(bob.value - 0.5) * 3}deg` }],
  }));
  // seen from the front, a spinning prop looks like a bar that keeps narrowing and widening
  const blade = useAnimatedStyle(() => ({
    transform: [{ scaleX: Math.max(0.12, Math.abs(Math.cos(spin.value * Math.PI))) }],
  }));
  const shadow = useAnimatedStyle(() => ({
    transform: [{ scaleX: 1 - 0.3 * bob.value }],
    opacity: 0.35 - 0.18 * bob.value,
  }));

  const pod = (side: 'left' | 'right') => (
    <View style={[styles.abs, { [side]: 4 * u, top: 8 * u, width: 52 * u, height: 32 * u }]}>
      <View style={[styles.abs, styles.disc, { left: 0, top: 4 * u, width: 52 * u, height: 8 * u, backgroundColor: bodyColor }]} />
      <Animated.View style={[styles.abs, { left: 2 * u, top: 6 * u, width: 48 * u, height: 4 * u, borderRadius: 2 * u, backgroundColor: bodyColor }, blade]} />
      <View style={[styles.abs, { left: 15 * u, top: 10 * u, width: 22 * u, height: 16 * u, borderRadius: 3 * u, backgroundColor: bodyColor }]} />
    </View>
  );

  return (
    <View style={{ width: W * u, height: H * u }}>
      <Animated.View style={[styles.abs, { left: 0, top: 0, width: W * u, height: 150 * u }, hover]}>
        {pod('left')}
        {pod('right')}
        {/* crossbar + body */}
        <View style={[styles.abs, { left: 28 * u, top: 28 * u, width: 104 * u, height: 10 * u, borderRadius: 3 * u, backgroundColor: bodyColor }]} />
        <View style={[styles.abs, { left: 60 * u, top: 22 * u, width: 40 * u, height: 26 * u, borderRadius: 7 * u, backgroundColor: bodyColor }]} />
        <View style={[styles.abs, { left: 76 * u, top: 36 * u, width: 8 * u, height: 8 * u, borderRadius: 4 * u, backgroundColor: legColor, opacity: 0.9 }]} />
        {/* legs + feet */}
        <View style={[styles.abs, { left: 36 * u, top: 50 * u, width: 8 * u, height: 72 * u, borderRadius: 4 * u, backgroundColor: legColor }]} />
        <View style={[styles.abs, { right: 36 * u, top: 50 * u, width: 8 * u, height: 72 * u, borderRadius: 4 * u, backgroundColor: legColor }]} />
        <View style={[styles.abs, { left: 28 * u, top: 118 * u, width: 24 * u, height: 6 * u, borderRadius: 3 * u, backgroundColor: legColor }]} />
        <View style={[styles.abs, { right: 28 * u, top: 118 * u, width: 24 * u, height: 6 * u, borderRadius: 3 * u, backgroundColor: legColor }]} />
      </Animated.View>
      {/* ground shadow stays on the ground */}
      <Animated.View style={[styles.abs, { left: 35 * u, top: 158 * u, width: 90 * u, height: 10 * u, borderRadius: 5 * u, backgroundColor: bodyColor }, shadow]} />
    </View>
  );
}

const styles = StyleSheet.create({
  abs: { position: 'absolute' },
  disc: { borderRadius: 999, opacity: 0.18 },
});
