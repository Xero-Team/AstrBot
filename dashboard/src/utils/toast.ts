import { useToastStore } from '@/stores/toast';
import type { ToastColor, ToastPayload } from '@/stores/toast';

type ToastOptions = Omit<ToastPayload, 'message' | 'color'>;

export function useToast() {
  const store = useToastStore();

  const toast = (
    message: string,
    color: ToastColor = 'info',
    opts: ToastOptions = {},
  ): void => {
    store.add({ message, color, ...opts });
  };

  return {
    toast,
    success: (msg: string, opts?: ToastOptions) => {
      toast(msg, 'success', opts);
    },
    error: (msg: string, opts?: ToastOptions) => {
      toast(msg, 'error', opts);
    },
    info: (msg: string, opts?: ToastOptions) => {
      toast(msg, 'primary', opts);
    },
    warning: (msg: string, opts?: ToastOptions) => {
      toast(msg, 'warning', opts);
    },
  };
}
