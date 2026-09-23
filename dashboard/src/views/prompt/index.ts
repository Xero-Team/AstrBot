/**
 * Prompt 管理相关组件
 *
 * 这些组件使用了 dashboard/src/components/folder 下的通用文件夹组件
 * 通过包装器模式将 promptStore 的状态和方法连接到通用组件
 */

// 主组件
export { default as PromptManager } from './PromptManager.vue';

// 文件夹相关组件
export { default as FolderTree } from './FolderTree.vue';
export { default as FolderBreadcrumb } from './FolderBreadcrumb.vue';
export { default as FolderCard } from './FolderCard.vue';

// 对话框组件
export { default as CreateFolderDialog } from './CreateFolderDialog.vue';
export { default as MoveToFolderDialog } from './MoveToFolderDialog.vue';

// Prompt 相关组件
export { default as PromptCard } from './PromptCard.vue';
