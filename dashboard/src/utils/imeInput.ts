const RECENT_COMPOSITION_END_THRESHOLD_MS = 100;

export function isComposingEnter(
  event: KeyboardEvent,
  compositionActive: boolean,
  lastCompositionEndAt: number | null = null,
): boolean {
  const hasCompositionKeyCodeFallback =
    typeof event.keyCode === 'number' && event.keyCode === 229;
  const isAfterRecentCompositionEnd =
    typeof event.timeStamp === 'number' &&
    typeof lastCompositionEndAt === 'number' &&
    event.timeStamp >= lastCompositionEndAt &&
    event.timeStamp - lastCompositionEndAt <
      RECENT_COMPOSITION_END_THRESHOLD_MS;

  return (
    event.key === 'Enter' &&
    (compositionActive ||
      event.isComposing ||
      hasCompositionKeyCodeFallback ||
      isAfterRecentCompositionEnd)
  );
}
