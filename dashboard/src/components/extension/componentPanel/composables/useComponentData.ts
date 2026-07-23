/**
 * 指令数据管理 Composable
 */
import { ref, reactive } from 'vue';
import { commandApi, toolApi } from '@/api/v1';
import { resolveErrorMessage } from '@/utils/errorUtils';
import type { CommandItem } from '@/domain/commands';
import type { ToolItem } from '@/domain/tools';
import type { CommandSummary, SnackbarState } from '../types';

export function useComponentData() {
  const loading = ref(false);
  const commands = ref<CommandItem[]>([]);
  const tools = ref<ToolItem[]>([]);
  const toolsLoading = ref(false);
  const summary = reactive<CommandSummary>({
    disabled: 0,
    conflicts: 0,
  });

  const snackbar = reactive<SnackbarState>({
    show: false,
    message: '',
    color: 'success',
  });

  /**
   * 显示 Toast 消息
   */
  const toast = (message: string, color: string = 'success') => {
    snackbar.message = message;
    snackbar.color = color;
    snackbar.show = true;
  };

  /**
   * 获取指令列表
   */
  const fetchCommands = async (errorMessage: string) => {
    loading.value = true;
    try {
      const res = await commandApi.list();
      if (res.data.status === 'ok') {
        commands.value = res.data.data.items || [];
        const s = res.data.data.summary || {};
        summary.disabled = s.disabled || 0;
        summary.conflicts = s.conflicts || 0;
      } else {
        toast(res.data.message || errorMessage, 'error');
      }
    } catch (err) {
      toast(resolveErrorMessage(err, errorMessage), 'error');
    } finally {
      loading.value = false;
    }
  };

  const fetchTools = async (errorMessage: string) => {
    toolsLoading.value = true;
    try {
      const res = await toolApi.list();
      if (res.data.status === 'ok') {
        tools.value = res.data.data || [];
      } else {
        toast(res.data.message || errorMessage, 'error');
      }
    } catch (err) {
      toast(resolveErrorMessage(err, errorMessage), 'error');
    } finally {
      toolsLoading.value = false;
    }
  };

  return {
    loading,
    commands,
    tools,
    toolsLoading,
    summary,
    snackbar,
    toast,
    fetchCommands,
    fetchTools,
  };
}
