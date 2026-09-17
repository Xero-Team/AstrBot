interface CopyToClipboardOptions {
  container?: HTMLElement | null;
}

export async function copyToClipboard(
  text: string,
  options: CopyToClipboardOptions = {},
): Promise<boolean> {
  if (!text) {
    return false;
  }

  if (
    typeof navigator !== 'undefined' &&
    navigator.clipboard &&
    window.isSecureContext
  ) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to execCommand.
    }
  }

  return fallbackCopy(text, options.container);
}

function fallbackCopy(text: string, container?: HTMLElement | null): boolean {
  if (typeof document === 'undefined' || !document.body) return false;

  const mountTarget =
    container && document.body.contains(container) ? container : document.body;
  const textArea = document.createElement('textarea');
  const activeElement =
    document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
  const selection = document.getSelection();
  const selectedRanges = selection
    ? Array.from({ length: selection.rangeCount }, (_, index) =>
        selection.getRangeAt(index).cloneRange(),
      )
    : [];

  textArea.value = text;
  textArea.readOnly = true;
  Object.assign(textArea.style, {
    position: 'fixed',
    left: '-9999px',
    top: '0',
    opacity: '0',
    pointerEvents: 'none',
  });

  mountTarget.appendChild(textArea);
  textArea.focus();
  textArea.select();
  textArea.setSelectionRange(0, text.length);

  try {
    return document.execCommand('copy');
  } catch {
    return false;
  } finally {
    if (textArea.parentNode) {
      textArea.parentNode.removeChild(textArea);
    }
    if (selection) {
      selection.removeAllRanges();
      selectedRanges.forEach((range) => {
        selection.addRange(range);
      });
    }
    activeElement?.focus?.();
  }
}
