/** Dronautics brand colors, from the design mockup: browns for the intro screens,
 *  peach for the control room, near-black panels, cream text. Fixed, not theme-dependent. */
export const Palette = {
  bark: '#6B5547', // splash background
  clay: '#8C7260', // connect screen background
  peach: '#E9A878', // control screen background
  ink: '#1A1A1A', // panels, primary buttons
  inkSoft: '#2A2622', // panel borders, pressed state
  cream: '#F6EFE8', // text on dark
  sand: '#C9AE9A', // "drone found" circle, secondary buttons
  mute: '#9A8878', // secondary text on dark panels
  ok: '#6FBF73',
  warn: '#F2B84B',
  danger: '#D6452E',
  blue: '#5AA9E6', // target on the map (matches the laptop HUD)
  orange: '#FF9A3C', // brace leg / lock color (matches the laptop HUD)
} as const;

export const Radius = { pill: 999, panel: 28, card: 18 } as const;
