import { Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';

import { Palette, Radius } from '@/constants/palette';

type Tone = 'ink' | 'sand' | 'danger' | 'ghost';

const toneStyle: Record<Tone, { bg: string; fg: string; border: string }> = {
  ink: { bg: Palette.ink, fg: Palette.cream, border: Palette.ink },
  sand: { bg: Palette.sand, fg: Palette.ink, border: Palette.sand },
  danger: { bg: Palette.danger, fg: Palette.cream, border: Palette.danger },
  ghost: { bg: 'transparent', fg: Palette.ink, border: Palette.ink },
};

type PillProps = {
  label: string;
  onPress?: () => void;
  onLongPress?: () => void;
  delayLongPress?: number;
  tone?: Tone;
  disabled?: boolean;
  small?: boolean;
  style?: StyleProp<ViewStyle>;
};

/** The wide rounded button from the mockup ("Settings", "CALIBRATE"). */
export function Pill({ label, onPress, onLongPress, delayLongPress, tone = 'ink', disabled, small, style }: PillProps) {
  const t = toneStyle[tone];
  return (
    <Pressable
      onPress={onPress}
      onLongPress={onLongPress}
      delayLongPress={delayLongPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.pill,
        small && styles.pillSmall,
        { backgroundColor: t.bg, borderColor: t.border, opacity: disabled ? 0.4 : pressed ? 0.7 : 1 },
        style,
      ]}>
      <Text style={[styles.pillText, small && styles.pillTextSmall, { color: t.fg }]}>{label}</Text>
    </Pressable>
  );
}

type RoundProps = {
  label: string;
  onPress?: () => void;
  size?: number;
  tone?: Tone;
  disabled?: boolean;
};

/** The round IN / OUT buttons. */
export function RoundButton({ label, onPress, size = 60, tone = 'ink', disabled }: RoundProps) {
  const t = toneStyle[tone];
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.round,
        { width: size, height: size, borderRadius: size / 2, backgroundColor: t.bg, borderColor: t.border },
        { opacity: disabled ? 0.4 : pressed ? 0.7 : 1 },
      ]}>
      <Text style={[styles.roundText, { color: t.fg }]}>{label}</Text>
    </Pressable>
  );
}

type ToggleProps = {
  label: string;
  on: boolean;
  onPress: () => void;
  disabled?: boolean;
  hint?: string;
};

/** Dark chip that lights up when on. */
export function Toggle({ label, on, onPress, disabled, hint }: ToggleProps) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.toggle,
        on ? styles.toggleOn : styles.toggleOff,
        { opacity: disabled ? 0.4 : pressed ? 0.7 : 1 },
      ]}>
      <View style={[styles.dot, { backgroundColor: on ? Palette.ok : Palette.mute }]} />
      <View>
        <Text style={[styles.toggleText, { color: on ? Palette.ink : Palette.cream }]}>{label}</Text>
        {hint ? <Text style={[styles.toggleHint, { color: on ? Palette.inkSoft : Palette.mute }]}>{hint}</Text> : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  pill: {
    alignSelf: 'stretch',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    paddingHorizontal: 20,
    borderRadius: Radius.pill,
    borderWidth: 2,
  },
  pillSmall: { paddingVertical: 9, paddingHorizontal: 14 },
  pillText: { fontSize: 17, fontWeight: '500', letterSpacing: 0.5 },
  pillTextSmall: { fontSize: 14 },
  round: { alignItems: 'center', justifyContent: 'center', borderWidth: 2 },
  roundText: { fontSize: 15, fontWeight: '600', letterSpacing: 1 },
  toggle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: Radius.card,
    minWidth: 0,
    flexGrow: 1,
    flexBasis: '45%',
  },
  toggleOn: { backgroundColor: Palette.sand },
  toggleOff: { backgroundColor: Palette.ink },
  toggleText: { fontSize: 15, fontWeight: '600', letterSpacing: 0.5 },
  toggleHint: { fontSize: 11, marginTop: 1 },
  dot: { width: 10, height: 10, borderRadius: 5 },
});
