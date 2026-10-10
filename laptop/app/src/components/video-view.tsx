/** The drone's camera. An MJPEG stream in a WebView: the raw one from hub.py, or the AMD-smoothed one. */
import { StyleSheet, Text, View } from 'react-native';
import { WebView } from 'react-native-webview';

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
  const html = `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>html,body{margin:0;height:100%;background:#000;overflow:hidden}img{width:100%;height:100%;object-fit:contain;display:block}</style>
</head><body><img src="${uri}"></body></html>`;
  return (
    <WebView
      key={uri}
      style={styles.web}
      originWhitelist={['*']}
      source={{ html }}
      scrollEnabled={false}
      bounces={false}
      mixedContentMode="always"
      allowsInlineMediaPlayback
      androidLayerType="hardware"
    />
  );
}

const styles = StyleSheet.create({
  web: { flex: 1, backgroundColor: '#000' },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#000' },
  emptyText: { color: Palette.mute, fontSize: 13, letterSpacing: 1 },
});
