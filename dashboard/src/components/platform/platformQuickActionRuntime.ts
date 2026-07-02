import type {
  QuickActionDefinition,
  QuickActionName,
} from '@/components/platform/platformQuickActions';

type Translate = (key: string) => string;

export interface QuickActionSummaryItem {
  label: string;
  value: string;
}

export function tryParseJsonRecord(
  value: string,
): Record<string, unknown> | null {
  if (!value.trim()) {
    return null;
  }
  try {
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return null;
    }
    return parsed as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function createInitialQuickActionForm(
  actionName: QuickActionName | '',
  definitions: Record<QuickActionName, QuickActionDefinition>,
): Record<string, string | number | boolean> {
  if (!actionName) {
    return {};
  }
  const definition = definitions[actionName];
  return Object.fromEntries(
    definition.fields.map((field) => [
      field.key,
      field.defaultValue ?? (field.kind === 'boolean' ? false : ''),
    ]),
  );
}

export function buildQuickActionPayload(
  actionName: QuickActionName,
  form: Record<string, string | number | boolean>,
  definitions: Record<QuickActionName, QuickActionDefinition>,
  tm: Translate,
): Record<string, unknown> {
  const definition = definitions[actionName];
  const payload: Record<string, unknown> = {};
  for (const field of definition.fields) {
    const rawValue = form[field.key];
    if (field.kind === 'boolean') {
      payload[field.key] = Boolean(rawValue);
      continue;
    }

    if (field.kind === 'number') {
      const stringValue = String(rawValue ?? '').trim();
      if (!stringValue) {
        continue;
      }
      const parsed = Number(stringValue);
      if (Number.isNaN(parsed)) {
        throw new Error(
          `${field.label}: ${tm('quickActions.validation.number')}`,
        );
      }
      payload[field.key] = parsed;
      continue;
    }

    if (field.kind === 'string-list') {
      const items = String(rawValue ?? '')
        .split(/[\n,]/)
        .map((item) => item.trim())
        .filter(Boolean);
      if (items.length > 0) {
        payload[field.key] = items;
      }
      continue;
    }

    const textValue = String(rawValue ?? '').trim();
    if (textValue) {
      payload[field.key] = textValue;
    }
  }
  return payload;
}

export function buildQuickActionResultSummary(
  resultText: string,
  tm: Translate,
): QuickActionSummaryItem[] {
  const payload = tryParseJsonRecord(resultText);
  if (!payload) {
    return [];
  }

  const summary: QuickActionSummaryItem[] = [];
  const status = typeof payload.status === 'string' ? payload.status : null;
  const retcode = payload.retcode;
  let message: string | null = null;
  if (typeof payload.message === 'string') {
    message = payload.message;
  } else if (typeof payload.wording === 'string') {
    message = payload.wording;
  }

  if (status) {
    summary.push({ label: tm('quickActions.summary.status'), value: status });
  }
  if (typeof retcode === 'number') {
    summary.push({
      label: tm('quickActions.summary.retcode'),
      value: String(retcode),
    });
  }
  if (message) {
    summary.push({
      label: tm('quickActions.summary.message'),
      value: message,
    });
  }

  if (
    payload.data &&
    typeof payload.data === 'object' &&
    !Array.isArray(payload.data)
  ) {
    const dataRecord = payload.data as Record<string, unknown>;
    for (const key of ['message_id', 'notice_id', 'file_id', 'user_id']) {
      const value = dataRecord[key];
      if (typeof value === 'string' || typeof value === 'number') {
        summary.push({
          label: key,
          value: String(value),
        });
      }
    }
  }

  return summary;
}
