const INVALID_ERROR_STRINGS = new Set([
  '[object Object]',
  'undefined',
  'null',
  '',
]);

const RESPONSE_MESSAGE_KEYS = ['message', 'error', 'detail', 'details', 'msg'];

interface ValidationIssueLike {
  loc?: unknown;
  msg?: unknown;
}

const formatValidationIssues = (value: unknown): string => {
  if (!Array.isArray(value)) {
    return '';
  }

  const issues = value
    .map((item) => {
      if (!item || typeof item !== 'object') {
        return '';
      }
      const issue = item as ValidationIssueLike;
      const message = typeof issue.msg === 'string' ? issue.msg.trim() : '';
      const loc = Array.isArray(issue.loc)
        ? issue.loc
            .map((part) => String(part).trim())
            .filter(Boolean)
            .join('.')
        : '';
      if (loc && message) {
        return `${loc}: ${message}`;
      }
      return message || loc;
    })
    .filter((item) => item.length > 0);

  return issues.join('; ');
};

interface ResponseLike {
  data?: unknown;
  statusText?: string;
}

interface ErrorLike {
  response?: ResponseLike;
  message?: string;
  toString?: () => string;
}

const pickResponseMessage = (responseData: unknown): string => {
  if (typeof responseData === 'string') {
    return responseData.trim();
  }
  if (!responseData || typeof responseData !== 'object') {
    return '';
  }

  const source = responseData as Record<string, unknown>;
  for (const key of RESPONSE_MESSAGE_KEYS) {
    const value = source[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
    const formattedIssues = formatValidationIssues(value);
    if (formattedIssues) {
      return formattedIssues;
    }
  }
  return '';
};

export const resolveErrorMessage = (
  err: unknown,
  fallbackMessage = '',
): string => {
  if (typeof err === 'string') {
    return err.trim() || fallbackMessage;
  }
  if (typeof err === 'number' || typeof err === 'boolean') {
    return String(err);
  }

  const error = err as ErrorLike | null | undefined;
  const fromResponse =
    pickResponseMessage(error?.response?.data) ||
    (typeof error?.response?.statusText === 'string'
      ? error.response.statusText.trim()
      : '');
  const fromError =
    typeof error?.message === 'string' ? error.message.trim() : '';

  let fromString = '';
  if (typeof error?.toString === 'function') {
    const value = error.toString().trim();
    fromString = INVALID_ERROR_STRINGS.has(value) ? '' : value;
  }

  return fromResponse || fromError || fromString || fallbackMessage;
};
