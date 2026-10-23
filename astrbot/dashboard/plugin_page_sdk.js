(() => {
  'use strict';

  const PROTOCOL = 'astrbot.dashboard-extension';
  const VERSION = 1;
  const MAX_PENDING = 64;
  const MAX_JSON_BYTES = 256 * 1024;
  const REQUEST_TIMEOUT_MS = 35_000;
  const encoder = new TextEncoder();
  const fragment = new URLSearchParams(location.hash.slice(1));
  const instanceId = fragment.get('instance');
  const nonce = fragment.get('channel');
  let generation = null;
  let port = null;
  let context = null;
  let disposed = false;
  const pending = new Map();
  const contextListeners = new Set();
  const objectUrls = new Set();
  let resolveReady;
  let rejectReady;
  const readyPromise = new Promise((resolve, reject) => {
    resolveReady = resolve;
    rejectReady = reject;
  });

  const exactKeys = (value, keys) => {
    if (!value || typeof value !== 'object' || Array.isArray(value))
      return false;
    const actual = Object.keys(value).sort();
    const expected = [...keys].sort();
    return (
      actual.length === expected.length &&
      actual.every((key, index) => key === expected[index])
    );
  };

  const messageSize = (value) => {
    try {
      return encoder.encode(
        JSON.stringify(value, (_key, item) =>
          item instanceof File ? null : item,
        ),
      ).length;
    } catch {
      return Number.POSITIVE_INFINITY;
    }
  };

  const publicError = (value) => {
    const error = new Error(
      typeof value?.message === 'string'
        ? value.message
        : 'Plugin request failed',
    );
    Object.defineProperties(error, {
      code: {
        value: typeof value?.code === 'string' ? value.code : 'request_failed',
        enumerable: true,
      },
      request_id: {
        value:
          typeof value?.request_id === 'string' ? value.request_id : undefined,
        enumerable: true,
      },
      retryable: { value: value?.retryable === true, enumerable: true },
    });
    return error;
  };

  const validContext = (value) =>
    exactKeys(value, [
      'protocol_version',
      'extension_id',
      'plugin_name',
      'page_id',
      'instance_id',
      'plugin_generation',
      'expires_at',
      'locale',
      'theme',
      'capabilities',
    ]) &&
    value.protocol_version === VERSION &&
    value.instance_id === instanceId &&
    typeof value.extension_id === 'string' &&
    typeof value.plugin_name === 'string' &&
    typeof value.page_id === 'string' &&
    typeof value.plugin_generation === 'string' &&
    typeof value.expires_at === 'string' &&
    typeof value.locale === 'string' &&
    exactKeys(value.theme, ['mode', 'is_dark', 'primary', 'secondary']) &&
    typeof value.theme.mode === 'string' &&
    typeof value.theme.is_dark === 'boolean' &&
    typeof value.theme.primary === 'string' &&
    typeof value.theme.secondary === 'string' &&
    exactKeys(value.capabilities, ['actions', 'upload', 'file']) &&
    Array.isArray(value.capabilities.actions) &&
    value.capabilities.actions.every((item) => typeof item === 'string') &&
    typeof value.capabilities.upload === 'boolean' &&
    typeof value.capabilities.file === 'boolean';

  const validPublicError = (value) => {
    const keys = Object.keys(value ?? {}).sort();
    const allowed = ['code', 'message', 'request_id', 'retryable'];
    return (
      value &&
      typeof value === 'object' &&
      keys.every((key) => allowed.includes(key)) &&
      keys.includes('code') &&
      keys.includes('message') &&
      keys.includes('retryable') &&
      typeof value.code === 'string' &&
      typeof value.message === 'string' &&
      typeof value.retryable === 'boolean' &&
      (value.request_id === undefined || typeof value.request_id === 'string')
    );
  };

  const rejectAll = (error) => {
    for (const [requestId, item] of pending) {
      clearTimeout(item.timer);
      item.reject(error);
      pending.delete(requestId);
    }
  };

  const close = (reason, notifyHost) => {
    if (disposed) return;
    disposed = true;
    if (notifyHost && port && generation) {
      port.postMessage({
        protocol_version: VERSION,
        instance_id: instanceId,
        plugin_generation: generation,
        kind: 'dispose',
        reason: 'page_requested',
      });
    }
    rejectAll(
      publicError({ code: 'disposed', message: reason, retryable: false }),
    );
    rejectReady(
      publicError({ code: 'disposed', message: reason, retryable: false }),
    );
    for (const url of objectUrls) URL.revokeObjectURL(url);
    objectUrls.clear();
    contextListeners.clear();
    if (port) port.close();
    port = null;
  };

  const validCommon = (value) =>
    value &&
    value.protocol_version === VERSION &&
    value.instance_id === instanceId &&
    value.plugin_generation === generation &&
    messageSize(value) <= MAX_JSON_BYTES;

  const handlePortMessage = (event) => {
    const message = event.data;
    if (
      generation === null &&
      exactKeys(message, [
        'protocol_version',
        'instance_id',
        'plugin_generation',
        'kind',
        'context',
      ]) &&
      message.protocol_version === VERSION &&
      message.instance_id === instanceId &&
      message.kind === 'context' &&
      typeof message.plugin_generation === 'string' &&
      message.plugin_generation &&
      validContext(message.context)
    ) {
      generation = message.plugin_generation;
    }
    if (!validCommon(message) || typeof message.kind !== 'string') {
      close('Protocol error', false);
      return;
    }
    if (message.kind === 'context') {
      if (
        !exactKeys(message, [
          'protocol_version',
          'instance_id',
          'plugin_generation',
          'kind',
          'context',
        ]) ||
        !validContext(message.context)
      ) {
        close('Protocol error', false);
        return;
      }
      context = message.context;
      resolveReady(context);
      for (const listener of contextListeners) listener(context);
      return;
    }
    if (message.kind === 'response') {
      const success = message.ok === true;
      const expected = success
        ? [
            'protocol_version',
            'instance_id',
            'plugin_generation',
            'kind',
            'request_id',
            'ok',
            'data',
          ]
        : [
            'protocol_version',
            'instance_id',
            'plugin_generation',
            'kind',
            'request_id',
            'ok',
            'error',
          ];
      if (
        !exactKeys(message, expected) ||
        typeof message.request_id !== 'string' ||
        (!success && !validPublicError(message.error))
      ) {
        close('Protocol error', false);
        return;
      }
      const item = pending.get(message.request_id);
      if (!item) return;
      pending.delete(message.request_id);
      clearTimeout(item.timer);
      if (success) item.resolve(message.data);
      else item.reject(publicError(message.error));
      return;
    }
    if (message.kind === 'cancelled') {
      if (
        !exactKeys(message, [
          'protocol_version',
          'instance_id',
          'plugin_generation',
          'kind',
          'request_id',
        ])
      ) {
        close('Protocol error', false);
        return;
      }
      const item = pending.get(message.request_id);
      if (!item) return;
      pending.delete(message.request_id);
      clearTimeout(item.timer);
      item.reject(
        publicError({
          code: 'cancelled',
          message: 'Request cancelled',
          retryable: true,
        }),
      );
      return;
    }
    if (message.kind === 'dispose') {
      if (
        !exactKeys(message, [
          'protocol_version',
          'instance_id',
          'plugin_generation',
          'kind',
          'reason',
        ]) ||
        ![
          'host_navigation',
          'plugin_changed',
          'logout',
          'expired',
          'protocol_error',
        ].includes(message.reason)
      ) {
        close('Protocol error', false);
        return;
      }
      event.target?.postMessage({
        protocol_version: VERSION,
        instance_id: instanceId,
        plugin_generation: generation,
        kind: 'disposed',
      });
      close('Plugin Page disposed by host', false);
      return;
    }
    if (
      message.kind !== 'disposed' ||
      !exactKeys(message, [
        'protocol_version',
        'instance_id',
        'plugin_generation',
        'kind',
      ])
    ) {
      close('Protocol error', false);
    }
  };

  const connect = (event) => {
    const message = event.data;
    if (
      event.source !== window.parent ||
      !exactKeys(message, [
        'protocol',
        'version',
        'kind',
        'instance_id',
        'nonce',
      ]) ||
      message.protocol !== PROTOCOL ||
      message.version !== VERSION ||
      message.kind !== 'connect' ||
      message.instance_id !== instanceId ||
      message.nonce !== nonce ||
      event.ports.length !== 1
    ) {
      return;
    }
    window.removeEventListener('message', connect);
    try {
      history.replaceState(null, '', `${location.pathname}${location.search}`);
    } catch {
      close('Protocol error', false);
      return;
    }
    port = event.ports[0];
    port.addEventListener('message', handlePortMessage);
    port.start();
  };

  const request = (actionId, actionKind, payload) => {
    if (disposed || !port || !generation)
      return Promise.reject(
        publicError({ code: 'not_ready', message: 'Plugin Page is not ready' }),
      );
    if (typeof actionId !== 'string' || pending.size >= MAX_PENDING) {
      return Promise.reject(
        publicError({
          code: 'request_rejected',
          message: 'Plugin request rejected',
        }),
      );
    }
    const requestId = crypto.randomUUID();
    const message = {
      protocol_version: VERSION,
      instance_id: instanceId,
      plugin_generation: generation,
      kind: 'request',
      request_id: requestId,
      action_id: actionId,
      action_kind: actionKind,
      ...payload,
    };
    if (messageSize(message) > MAX_JSON_BYTES) {
      return Promise.reject(
        publicError({
          code: 'message_too_large',
          message: 'Plugin request is too large',
        }),
      );
    }
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (!pending.delete(requestId)) return;
        port?.postMessage({
          protocol_version: VERSION,
          instance_id: instanceId,
          plugin_generation: generation,
          kind: 'cancel',
          request_id: requestId,
        });
        reject(
          publicError({
            code: 'timeout',
            message: 'Plugin request timed out',
            retryable: true,
          }),
        );
      }, REQUEST_TIMEOUT_MS);
      pending.set(requestId, { resolve, reject, timer });
      try {
        port.postMessage(message);
      } catch (error) {
        pending.delete(requestId);
        clearTimeout(timer);
        reject(publicError({
          code: 'internal',
          message: 'Plugin request could not be sent',
          retryable: false,
        }));
      }
    });
  };

  const api = Object.freeze({
    ready: () => readyPromise,
    invoke: (actionId, payload) => request(actionId, 'json', { payload }),
    upload: (actionId, file, fields) => {
      if (!(file instanceof File))
        return Promise.reject(new TypeError('file must be a File'));
      return request(actionId, 'upload', { file, fields });
    },
    readFile: async (actionId, payload) => {
      const value = await request(actionId, 'file', {
        file_operation: 'read',
        payload,
      });
      if (
        !value ||
        !(value.bytes instanceof ArrayBuffer) ||
        value.disposition !== 'inline'
      ) {
        throw publicError({
          code: 'invalid_file',
          message: 'Invalid file response',
        });
      }
      return value;
    },
    download: async (actionId, payload) => {
      await request(actionId, 'file', { file_operation: 'download', payload });
    },
    createObjectURL: (file) => {
      if (
        !file ||
        !(file.bytes instanceof ArrayBuffer) ||
        file.disposition !== 'inline'
      )
        throw new TypeError('Invalid PageFileBuffer');
      const url = URL.createObjectURL(
        new Blob([file.bytes], { type: file.contentType }),
      );
      objectUrls.add(url);
      return url;
    },
    revokeObjectURL: (url) => {
      if (objectUrls.delete(url)) URL.revokeObjectURL(url);
    },
    onContext: (listener) => {
      if (typeof listener !== 'function')
        throw new TypeError('listener must be a function');
      contextListeners.add(listener);
      if (context !== null) listener(context);
      return () => contextListeners.delete(listener);
    },
    dispose: () => close('Plugin Page disposed', true),
  });

  Object.defineProperty(window, 'AstrBotPluginPage', {
    value: api,
    writable: false,
    configurable: false,
    enumerable: true,
  });

  if (!instanceId || !nonce) {
    close('Protocol error', false);
    return;
  }
  window.addEventListener('message', connect);
  window.parent.postMessage(
    {
      protocol: PROTOCOL,
      version: VERSION,
      kind: 'ready',
      instance_id: instanceId,
      nonce,
    },
    '*',
  );
})();
