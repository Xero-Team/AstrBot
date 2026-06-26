export type DesktopRuntimeInfo = {
  bridge: Window['astrbotDesktop'] | undefined;
  hasDesktopRuntimeProbe: boolean;
  hasDesktopRestartCapability: boolean;
  isDesktopRuntime: boolean;
};

export async function getDesktopRuntimeInfo(): Promise<DesktopRuntimeInfo> {
  const bridge = window.astrbotDesktop;
  const hasBridge = bridge !== undefined;
  const hasDesktopRuntimeProbe =
    hasBridge && typeof bridge.isDesktopRuntime === 'function';
  const hasDesktopRestartCapability =
    hasBridge &&
    typeof bridge.restartBackend === 'function' &&
    hasDesktopRuntimeProbe;

  let isDesktopRuntime = Boolean(bridge?.isDesktop);
  if (hasDesktopRuntimeProbe) {
    try {
      isDesktopRuntime =
        isDesktopRuntime || Boolean(await bridge.isDesktopRuntime());
    } catch (error) {
      console.warn(
        '[desktop-runtime] Failed to detect desktop runtime.',
        error,
      );
    }
  }

  return {
    bridge,
    hasDesktopRuntimeProbe,
    hasDesktopRestartCapability,
    isDesktopRuntime,
  };
}
