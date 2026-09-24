const PROVIDER_ICONS: Record<string, string> = {
  openai: new URL('@/assets/images/provider_logos/openai.svg', import.meta.url)
    .href,
  azure: new URL('@/assets/images/provider_logos/azure.svg', import.meta.url)
    .href,
  xai: new URL('@/assets/images/provider_logos/xai.svg', import.meta.url).href,
  anthropic: new URL(
    '@/assets/images/provider_logos/anthropic.svg',
    import.meta.url,
  ).href,
  ollama: new URL('@/assets/images/provider_logos/ollama.svg', import.meta.url)
    .href,
  google: new URL(
    '@/assets/images/provider_logos/gemini-color.svg',
    import.meta.url,
  ).href,
  deepseek: new URL(
    '@/assets/images/provider_logos/deepseek.svg',
    import.meta.url,
  ).href,
  modelscope: new URL(
    '@/assets/images/provider_logos/modelscope.svg',
    import.meta.url,
  ).href,
  zhipu: new URL('@/assets/images/provider_logos/zhipu.svg', import.meta.url)
    .href,
  nvidia: new URL(
    '@/assets/images/provider_logos/nvidia-color.svg',
    import.meta.url,
  ).href,
  siliconflow: new URL(
    '@/assets/images/provider_logos/siliconcloud.svg',
    import.meta.url,
  ).href,
  moonshot: new URL('@/assets/images/provider_logos/kimi.svg', import.meta.url)
    .href,
  kimi: new URL('@/assets/images/provider_logos/kimi.svg', import.meta.url)
    .href,
  'kimi-code': new URL(
    '@/assets/images/provider_logos/kimi.svg',
    import.meta.url,
  ).href,
  longcat: new URL(
    '@/assets/images/provider_logos/longcat-color.svg',
    import.meta.url,
  ).href,
  ppio: new URL('@/assets/images/provider_logos/ppio.svg', import.meta.url)
    .href,
  dify: new URL(
    '@/assets/images/provider_logos/dify-color.svg',
    import.meta.url,
  ).href,
  coze: new URL('@/assets/images/provider_logos/coze.svg', import.meta.url)
    .href,
  dashscope: new URL(
    '@/assets/images/provider_logos/alibabacloud-color.svg',
    import.meta.url,
  ).href,
  deerflow: new URL('@/assets/images/provider_logos/deer.svg', import.meta.url)
    .href,
  fastgpt: new URL(
    '@/assets/images/provider_logos/fastgpt-color.svg',
    import.meta.url,
  ).href,
  lm_studio: new URL(
    '@/assets/images/provider_logos/lmstudio.svg',
    import.meta.url,
  ).href,
  fishaudio: new URL(
    '@/assets/images/provider_logos/fishaudio.svg',
    import.meta.url,
  ).href,
  minimax: new URL(
    '@/assets/images/provider_logos/minimax.svg',
    import.meta.url,
  ).href,
  'minimax-token-plan': new URL(
    '@/assets/images/provider_logos/minimax.svg',
    import.meta.url,
  ).href,
  mimo: new URL('@/assets/images/provider_logos/xiaomi.svg', import.meta.url)
    .href,
  xiaomi: new URL('@/assets/images/provider_logos/xiaomi.svg', import.meta.url)
    .href,
  'xiaomi-token-plan': new URL(
    '@/assets/images/provider_logos/xiaomi.svg',
    import.meta.url,
  ).href,
  '302ai': new URL(
    '@/assets/images/provider_logos/ai302-color.svg',
    import.meta.url,
  ).href,
  microsoft: new URL(
    '@/assets/images/provider_logos/microsoft.svg',
    import.meta.url,
  ).href,
  vllm: new URL('@/assets/images/provider_logos/vllm.svg', import.meta.url)
    .href,
  groq: new URL('@/assets/images/provider_logos/groq.svg', import.meta.url)
    .href,
  aihubmix: new URL(
    '@/assets/images/provider_logos/aihubmix-color.svg',
    import.meta.url,
  ).href,
  openrouter: new URL(
    '@/assets/images/provider_logos/openrouter.svg',
    import.meta.url,
  ).href,
  'opencode-go': new URL(
    '@/assets/images/provider_logos/opencode.svg',
    import.meta.url,
  ).href,
  ssycloud: new URL(
    '@/assets/images/provider_logos/shengsuanyun.png',
    import.meta.url,
  ).href,
  tokenpony: new URL(
    '@/assets/images/provider_logos/tokenpony.png',
    import.meta.url,
  ).href,
  compshare: new URL(
    '@/assets/images/provider_logos/compshare.ico',
    import.meta.url,
  ).href,
  xinference: new URL(
    '@/assets/images/provider_logos/xinference-color.svg',
    import.meta.url,
  ).href,
  bailian: new URL(
    '@/assets/images/provider_logos/bailian-color.svg',
    import.meta.url,
  ).href,
  volcengine: new URL(
    '@/assets/images/provider_logos/volcengine-color.svg',
    import.meta.url,
  ).href,
  typesafe: new URL(
    '@/assets/images/provider_logos/typesafe.svg',
    import.meta.url,
  ).href,
};

interface ProviderDescriptionTemplate {
  type?: string;
  provider?: string;
}

export function getProviderIcon(type: string): string {
  return PROVIDER_ICONS[type] || '';
}

const PROVIDER_DISPLAY_NAMES: Record<string, string> = {
  jev_systemone: 'JEV System One',
};

export function getProviderDisplayName(
  type: string | undefined,
  fallback: string,
): string {
  return (type && PROVIDER_DISPLAY_NAMES[type]) || fallback;
}

const MONOCHROME_PROVIDER_ICONS = new Set([
  'openai',
  'azure',
  'xai',
  'anthropic',
  'ollama',
  'deepseek',
  'modelscope',
  'zhipu',
  'siliconflow',
  'moonshot',
  'kimi',
  'kimi-code',
  'ppio',
  'lm_studio',
  'minimax',
  'minimax-token-plan',
  'mimo',
  'xiaomi',
  'xiaomi-token-plan',
  'openrouter',
  'opencode-go',
  'typesafe',
]);

export function isMonochromeProviderIcon(type: string): boolean {
  return MONOCHROME_PROVIDER_ICONS.has(type);
}

export function getProviderDescription(
  template: ProviderDescriptionTemplate,
  name: string,
  tm: (key: string, params?: Record<string, string | number>) => string,
): string {
  const type = template.type ?? '';

  if (type === 'jev_systemone') {
    return tm('providers.description.jev_systemone');
  }

  if (type === 'openai_chat_completions') {
    return tm('providers.description.openai_chat_completions');
  }
  if (type === 'openai_responses') {
    return tm('providers.description.openai_responses');
  }
  if (name === 'OpenAI') {
    return tm('providers.description.openai', { type });
  }
  if (template.provider === 'kimi-code') {
    return tm('providers.description.kimi_code');
  }
  if (type === 'opencode_go_chat_completion') {
    return tm('providers.description.opencode_go_chat_completion');
  }
  if (type === 'opencode_go_messages') {
    return tm('providers.description.opencode_go_messages');
  }
  if (type === 'opencode_go_responses') {
    return tm('providers.description.opencode_go_responses');
  }
  if (name === 'vLLM Rerank') {
    return tm('providers.description.vllm_rerank', { type });
  }
  return tm('providers.description.default', { type });
}
