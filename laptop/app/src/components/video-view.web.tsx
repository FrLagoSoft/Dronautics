/** Web build: the browser shows an MJPEG stream in a plain <img>, no WebView needed. */
import { Image, StyleSheet, Text, View } from 'react-native';

import { Palette } from '@/constants/palette';

type Props = { uri: string | null; label?: string };

export function VideoView({ uri, label }: Props) {
  if (!uri) {
    return (
      <View style={styles.empty}>
        <Text style={styles.emptyText}>{label ?? 'no video'}</Text>
      </View>
    );
  }
  return <Image source={{ uri }} style={styles.img} resizeMode="contain" />;
}

const styles = StyleSheet.create({
  img: { flex: 1, backgroundColor: '#000' },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#000' },
  emptyText: { color: Palette.mute, fontSize: 13, letterSpacing: 1 },
});
