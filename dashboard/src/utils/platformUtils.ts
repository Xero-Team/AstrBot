const PLATFORM_ICON_URLS: Record<string, string> = {
  aiocqhttp: new URL(
    '@/assets/images/platform_logos/onebot.png',
    import.meta.url,
  ).href,
  napcat: new URL('@/assets/images/platform_logos/napcat.png', import.meta.url)
    .href,
  qq_official: new URL('@/assets/images/platform_logos/qq.png', import.meta.url)
    .href,
  qq_official_webhook: new URL(
    '@/assets/images/platform_logos/qq.png',
    import.meta.url,
  ).href,
  weixin_oc: new URL(
    '@/assets/images/platform_logos/wechat.png',
    import.meta.url,
  ).href,
  wecom: new URL('@/assets/images/platform_logos/wecom.png', import.meta.url)
    .href,
  wecom_ai_bot: new URL(
    '@/assets/images/platform_logos/wecom.png',
    import.meta.url,
  ).href,
  weixin_official_account: new URL(
    '@/assets/images/platform_logos/wechat.png',
    import.meta.url,
  ).href,
  lark: new URL('@/assets/images/platform_logos/lark.png', import.meta.url)
    .href,
  dingtalk: new URL(
    '@/assets/images/platform_logos/dingtalk.svg',
    import.meta.url,
  ).href,
  telegram: new URL(
    '@/assets/images/platform_logos/telegram.svg',
    import.meta.url,
  ).href,
  discord: new URL(
    '@/assets/images/platform_logos/discord.svg',
    import.meta.url,
  ).href,
  slack: new URL('@/assets/images/platform_logos/slack.svg', import.meta.url)
    .href,
  kook: new URL('@/assets/images/platform_logos/kook.png', import.meta.url)
    .href,
  satori: new URL('@/assets/images/platform_logos/satori.png', import.meta.url)
    .href,
  Satori: new URL('@/assets/images/platform_logos/satori.png', import.meta.url)
    .href,
  misskey: new URL(
    '@/assets/images/platform_logos/misskey.png',
    import.meta.url,
  ).href,
  line: new URL('@/assets/images/platform_logos/line.png', import.meta.url)
    .href,
  matrix: new URL('@/assets/images/platform_logos/matrix.svg', import.meta.url)
    .href,
  mattermost: new URL(
    '@/assets/images/platform_logos/mattermost.svg',
    import.meta.url,
  ).href,
};

const TUTORIAL_LINKS: Record<string, string> = {
  qq_official_webhook:
    'https://docs.astrbot.app/platform/qqofficial/webhook.html',
  qq_official: 'https://docs.astrbot.app/platform/qqofficial/websockets.html',
  aiocqhttp: 'https://docs.astrbot.app/platform/aiocqhttp.html',
  napcat: 'https://docs.astrbot.app/platform/napcat.html',
  wecom: 'https://docs.astrbot.app/platform/wecom.html',
  weixin_oc: 'https://docs.astrbot.app/platform/weixin_oc.html',
  wecom_ai_bot: 'https://docs.astrbot.app/platform/wecom_ai_bot.html',
  lark: 'https://docs.astrbot.app/platform/lark.html',
  telegram: 'https://docs.astrbot.app/platform/telegram.html',
  dingtalk: 'https://docs.astrbot.app/platform/dingtalk.html',
  weixin_official_account:
    'https://docs.astrbot.app/platform/weixin-official-account.html',
  discord: 'https://docs.astrbot.app/platform/discord.html',
  slack: 'https://docs.astrbot.app/platform/slack.html',
  kook: 'https://docs.astrbot.app/platform/kook.html',
  vocechat: 'https://docs.astrbot.app/platform/vocechat.html',
  satori: 'https://docs.astrbot.app/platform/satori/llonebot.html',
  misskey: 'https://docs.astrbot.app/platform/misskey.html',
  line: 'https://docs.astrbot.app/platform/line.html',
  matrix: 'https://docs.astrbot.app/platform/matrix.html',
};

const PLATFORM_DISPLAY_NAMES: Record<string, string> = {
  aiocqhttp: 'aiocqhttp (OneBot v11)',
  napcat: 'napcat (NapCat WebSocket)',
  qq_official: 'qq_official (QQ 官方机器人平台)',
  weixin_official_account: 'weixin_official_account (微信公众号)',
  wecom: 'wecom (企业微信应用)',
  wecom_ai_bot: 'wecom_ai_bot (企业微信智能机器人)',
  lark: 'lark (飞书)',
  dingtalk: 'dingtalk (钉钉)',
  telegram: 'telegram (Telegram)',
  discord: 'discord (Discord)',
  misskey: 'misskey (Misskey)',
  slack: 'slack (Slack)',
  kook: 'kook (KOOK)',
  vocechat: 'vocechat (VoceChat)',
  satori: 'satori (Satori)',
  line: 'line (LINE)',
  matrix: 'matrix (Matrix)',
};

const PLATFORM_COLORS: Record<string, string> = {
  aiocqhttp: 'blue',
  napcat: 'blue',
  qq_official: 'purple',
  telegram: 'light-blue',
  discord: 'indigo',
  webchat: 'orange',
};

interface PlatformTemplate {
  [key: string]: unknown;
}

export function getPlatformIcon(name: string): string | undefined {
  return PLATFORM_ICON_URLS[name];
}

export function getTutorialLink(platformType: string): string {
  return TUTORIAL_LINKS[platformType] || 'https://docs.astrbot.app';
}

export function getPlatformDescription(
  _template: PlatformTemplate,
  name: string,
): string {
  if (name.includes('vocechat')) {
    return '由 @HikariFroya 提供。';
  }
  if (name.includes('kook')) {
    return '由 @wuyan1003 提供。';
  }
  return '';
}

export function getPlatformDisplayName(platformId: string): string {
  return PLATFORM_DISPLAY_NAMES[platformId] || platformId;
}

export function getPlatformColor(platformId: string): string {
  return PLATFORM_COLORS[platformId] || 'grey';
}
