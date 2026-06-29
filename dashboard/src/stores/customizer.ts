import { defineStore } from 'pinia';
import config, {
  getInitialSystemPrefersDark,
  type ThemeMode,
  resolveUiTheme,
} from '@/config';

const DARK_THEMES: ReadonlySet<string> = new Set(['PurpleThemeDark']);

export const useCustomizerStore = defineStore('customizer', {
  state: () => ({
    Sidebar_drawer: config.Sidebar_drawer,
    Customizer_drawer: config.Customizer_drawer,
    mini_sidebar: config.mini_sidebar,
    fontTheme: 'Noto Sans SC',
    themeMode: config.themeMode,
    systemPrefersDark: getInitialSystemPrefersDark(),
    inputBg: config.inputBg,
    chatSidebarOpen: false, // chat mode mobile sidebar state
  }),

  getters: {
    uiTheme: (state) => {
      if (state.themeMode !== 'system') {
        return resolveUiTheme(state.themeMode);
      }
      return state.systemPrefersDark ? 'PurpleThemeDark' : 'PurpleTheme';
    },
    isDark(): boolean {
      return DARK_THEMES.has(this.uiTheme);
    },
  },

  actions: {
    SET_SIDEBAR_DRAWER() {
      this.Sidebar_drawer = !this.Sidebar_drawer;
    },
    SET_MINI_SIDEBAR(payload: boolean) {
      this.mini_sidebar = payload;
    },
    SET_FONT(payload: string) {
      this.fontTheme = payload;
    },

    SET_THEME_MODE(mode: ThemeMode) {
      this.themeMode = mode;
      localStorage.setItem('themeMode', mode);
    },

    SET_SYSTEM_PREFERS_DARK(prefersDark: boolean) {
      this.systemPrefersDark = prefersDark;
    },

    TOGGLE_CHAT_SIDEBAR() {
      this.chatSidebarOpen = !this.chatSidebarOpen;
    },
    SET_CHAT_SIDEBAR(payload: boolean) {
      this.chatSidebarOpen = payload;
    },
  },
});
