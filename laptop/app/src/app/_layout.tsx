import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { Palette } from '@/constants/palette';
import { HubProvider } from '@/lib/hub';
import { SettingsProvider } from '@/lib/settings';

export default function RootLayout() {
  return (
    <SettingsProvider>
      <HubProvider>
        <StatusBar style="light" />
        <Stack
          screenOptions={{
            headerShown: false,
            animation: 'fade',
            contentStyle: { backgroundColor: Palette.bark },
          }}>
          <Stack.Screen name="index" />
          <Stack.Screen name="connect" options={{ contentStyle: { backgroundColor: Palette.clay } }} />
          <Stack.Screen name="control" options={{ contentStyle: { backgroundColor: Palette.peach } }} />
          <Stack.Screen name="sim" options={{ contentStyle: { backgroundColor: Palette.peach } }} />
          <Stack.Screen
            name="settings"
            options={{ presentation: 'modal', contentStyle: { backgroundColor: Palette.clay } }}
          />
        </Stack>
      </HubProvider>
    </SettingsProvider>
  );
}
