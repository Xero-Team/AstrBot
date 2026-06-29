export type ThemeMode = 'light' | 'dark' | 'system';

export type ConfigProps = {
  Sidebar_drawer: boolean;
  Customizer_drawer: boolean;
  mini_sidebar: boolean;
  fontTheme: string;
  themeMode: ThemeMode;
  inputBg: boolean;
};

function checkThemeMode(): ThemeMode {
  const mode = localStorage.getItem('themeMode') as ThemeMode | null;
  if (mode === 'light' || mode === 'dark' || mode === 'system') return mode;

  localStorage.setItem('themeMode', 'system');
  return 'system';
}

export function resolveUiTheme(mode: ThemeMode): string {
  if (mode === 'dark') return 'PurpleThemeDark';
  if (mode === 'light') return 'PurpleTheme';
  return getSystemUiTheme();
}

export function getSystemUiTheme(): string {
  const prefersDark =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches;
  return prefersDark ? 'PurpleThemeDark' : 'PurpleTheme';
}

export function getInitialSystemPrefersDark(): boolean {
  return getSystemUiTheme() === 'PurpleThemeDark';
}

const themeMode = checkThemeMode();

const config: ConfigProps = {
  Sidebar_drawer: true,
  Customizer_drawer: false,
  mini_sidebar: false,
  fontTheme: 'Roboto',
  themeMode,
  inputBg: false,
};

export default config;
