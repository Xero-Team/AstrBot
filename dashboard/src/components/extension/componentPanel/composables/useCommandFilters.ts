/**
 * 指令过滤逻辑 Composable
 */
import { ref, computed, type Ref } from 'vue';
import type { CommandItem } from '@/domain/commands';
import { normalizeTextInput } from '@/utils/inputValue';

// Matches the default `Array.prototype.sort()` order (UTF-16 code units) so the
// filter dropdowns keep the ordering they had before an explicit comparator was
// required by `@typescript-eslint/require-array-sort-compare`.
const compareCodeUnits = (a: string, b: string): number => {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
};

export function useCommandFilters(commands: Ref<CommandItem[]>) {
  // 过滤状态
  const searchQuery = ref('');
  const pluginFilter = ref('all');
  const actionFilter = ref('all');
  const statusFilter = ref('all');
  const typeFilter = ref('all');
  const showSystemPlugins = ref(false);

  // 展开的指令组
  const expandedGroups = ref<Set<string>>(new Set());

  /**
   * 检查是否有涉及系统插件的冲突
   */
  const hasSystemPluginConflict = computed(() => {
    return commands.value.some((cmd) => cmd.has_conflict && cmd.reserved);
  });

  /**
   * 实际是否显示系统插件（如果有系统插件冲突则强制显示）
   */
  const effectiveShowSystemPlugins = computed(() => {
    return showSystemPlugins.value || hasSystemPluginConflict.value;
  });

  /**
   * 获取可用的插件列表（用于过滤下拉框）
   */
  const availablePlugins = computed(() => {
    const plugins = new Set(
      commands.value
        .filter((cmd) => effectiveShowSystemPlugins.value || !cmd.reserved)
        .map((cmd) => cmd.plugin),
    );
    return Array.from(plugins).sort(compareCodeUnits);
  });

  const availableActions = computed(() =>
    Array.from(
      new Set(
        commands.value
          .map((cmd) => cmd.action)
          .filter((action): action is string => Boolean(action)),
      ),
    ).sort(compareCodeUnits),
  );

  const matchesSearchQuery = (cmd: CommandItem, query: string): boolean => {
    return Boolean(
      cmd.effective_command?.toLowerCase().includes(query) ||
      cmd.signature?.toLowerCase().includes(query) ||
      cmd.display_signature?.toLowerCase().includes(query) ||
      cmd.description?.toLowerCase().includes(query) ||
      cmd.plugin?.toLowerCase().includes(query),
    );
  };

  const matchesStatusFilter = (cmd: CommandItem): boolean => {
    const filter = statusFilter.value;
    if (filter === 'all') return true;
    if (filter === 'enabled') return Boolean(cmd.enabled);
    if (filter === 'disabled') return !cmd.enabled;
    if (filter === 'conflict') return Boolean(cmd.has_conflict);
    return true;
  };

  const matchesTypeFilter = (cmd: CommandItem): boolean => {
    const filter = typeFilter.value;
    if (filter === 'all') return true;
    if (filter === 'group') return cmd.type === 'group';
    if (filter === 'command') return cmd.type === 'command';
    if (filter === 'sub_command') return cmd.type === 'sub_command';
    return true;
  };

  /**
   * 检查指令是否匹配过滤条件
   */
  const matchesFilters = (cmd: CommandItem, query: string): boolean => {
    // 系统插件过滤（除非显示系统插件）
    if (!effectiveShowSystemPlugins.value && cmd.reserved) {
      return false;
    }

    // 搜索过滤
    if (query && !matchesSearchQuery(cmd, query)) {
      return false;
    }

    // 插件过滤
    if (pluginFilter.value !== 'all' && cmd.plugin !== pluginFilter.value) {
      return false;
    }

    // Authorization action filter
    if (actionFilter.value !== 'all' && cmd.action !== actionFilter.value) {
      return false;
    }

    // 状态过滤
    if (!matchesStatusFilter(cmd)) {
      return false;
    }

    // 类型过滤
    if (!matchesTypeFilter(cmd)) {
      return false;
    }

    return true;
  };

  interface CommandBuckets {
    conflict: CommandItem[];
    normal: CommandItem[];
  }

  const bucketCommand = (buckets: CommandBuckets, cmd: CommandItem): void => {
    if (cmd.has_conflict) {
      buckets.conflict.push(cmd);
    } else {
      buckets.normal.push(cmd);
    }
  };

  const collectGroupMatches = (
    cmd: CommandItem,
    query: string,
    buckets: CommandBuckets,
  ): void => {
    const groupMatches = matchesFilters(cmd, query);
    const matchingSubCmds = (cmd.sub_commands || []).filter((sub) =>
      matchesFilters(sub, query),
    );

    // 如果组匹配或有匹配的子指令，则包含它
    if (!groupMatches && matchingSubCmds.length === 0) return;

    bucketCommand(buckets, cmd);

    // 如果组已展开，添加匹配的子指令
    if (!expandedGroups.value.has(cmd.command_id)) return;
    for (const sub of matchingSubCmds) {
      bucketCommand(buckets, sub);
    }
  };

  /**
   * 过滤后的指令列表（支持层级结构）
   */
  const filteredCommands = computed(() => {
    const query = normalizeTextInput(searchQuery.value).toLowerCase();
    const buckets: CommandBuckets = { conflict: [], normal: [] };

    for (const cmd of commands.value) {
      // 对于指令组，检查组本身或子指令是否匹配
      if (cmd.is_group) {
        collectGroupMatches(cmd, query, buckets);
      } else if (cmd.type !== 'sub_command' && matchesFilters(cmd, query)) {
        // 普通指令（子指令通过组处理）
        bucketCommand(buckets, cmd);
      }
    }

    // 按 effective_command 排序冲突指令，使其分组在一起
    buckets.conflict.sort((a, b) =>
      (a.effective_command || '').localeCompare(b.effective_command || ''),
    );

    return [...buckets.conflict, ...buckets.normal];
  });

  /**
   * 切换指令组的展开/折叠状态
   */
  const toggleGroupExpand = (cmd: CommandItem) => {
    if (!cmd.is_group) return;
    if (expandedGroups.value.has(cmd.command_id)) {
      expandedGroups.value.delete(cmd.command_id);
    } else {
      expandedGroups.value.add(cmd.command_id);
    }
  };

  /**
   * 检查指令组是否已展开
   */
  const isGroupExpanded = (cmd: CommandItem): boolean => {
    return expandedGroups.value.has(cmd.command_id);
  };

  return {
    // 状态
    searchQuery,
    pluginFilter,
    actionFilter,
    statusFilter,
    typeFilter,
    showSystemPlugins,
    expandedGroups,

    // 计算属性
    hasSystemPluginConflict,
    effectiveShowSystemPlugins,
    availablePlugins,
    availableActions,
    filteredCommands,

    // 方法
    matchesFilters,
    toggleGroupExpand,
    isGroupExpanded,
  };
}
