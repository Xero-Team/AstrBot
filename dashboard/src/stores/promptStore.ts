/**
 * Prompt 文件夹管理 Store
 */
import { defineStore } from 'pinia';
import { promptApi } from '@/api/v1';

// 类型定义
export interface PromptFolder {
  folder_id: string;
  name: string;
  parent_id: string | null;
  description: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface Prompt {
  prompt_id: string;
  system_prompt: string;
  custom_error_message: string | null;
  begin_dialogs: string[];
  tools: string[] | null;
  skills: string[] | null;
  folder_id: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface FolderTreeNode {
  folder_id: string;
  name: string;
  parent_id: string | null;
  description: string | null;
  sort_order: number;
  children: FolderTreeNode[];
}

export interface ReorderItem {
  id: string;
  type: 'prompt' | 'folder';
  sort_order: number;
}

export const usePromptStore = defineStore('prompt', {
  state: () => ({
    folderTree: [] as FolderTreeNode[],
    currentFolderId: null as string | null,
    currentFolders: [] as PromptFolder[],
    currentPrompts: [] as Prompt[],
    breadcrumbPath: [] as FolderTreeNode[],
    expandedFolderIds: [] as string[], // Store expanded folder IDs
    loading: false,
    treeLoading: false,
  }),

  getters: {
    // 当前文件夹名称
    currentFolderName(): string {
      if (this.breadcrumbPath.length === 0) {
        return '根目录';
      }
      return (
        this.breadcrumbPath[this.breadcrumbPath.length - 1]?.name || '根目录'
      );
    },
  },

  actions: {
    /**
     * Toggle folder expansion state
     */
    toggleFolderExpansion(folderId: string) {
      const index = this.expandedFolderIds.indexOf(folderId);
      if (index === -1) {
        this.expandedFolderIds.push(folderId);
      } else {
        this.expandedFolderIds.splice(index, 1);
      }
    },

    /**
     * Set folder expansion state
     */
    setFolderExpansion(folderId: string, expanded: boolean) {
      const index = this.expandedFolderIds.indexOf(folderId);
      if (expanded && index === -1) {
        this.expandedFolderIds.push(folderId);
      } else if (!expanded && index !== -1) {
        this.expandedFolderIds.splice(index, 1);
      }
    },

    /**
     * 加载文件夹树形结构
     */
    async loadFolderTree(): Promise<void> {
      this.treeLoading = true;
      try {
        const response = await promptApi.tree();
        if (response.data.status === 'ok') {
          this.folderTree = response.data.data || [];
        } else {
          throw new Error(response.data.message || '获取文件夹树失败');
        }
      } finally {
        this.treeLoading = false;
      }
    },

    /**
     * 导航到指定文件夹
     */
    async navigateToFolder(folderId: string | null): Promise<void> {
      this.loading = true;
      try {
        this.currentFolderId = folderId;

        // 并行加载子文件夹和 Prompt
        const [foldersRes, promptsRes] = await Promise.all([
          promptApi.folders(folderId),
          promptApi.list(folderId),
        ]);

        if (foldersRes.data.status === 'ok') {
          this.currentFolders = foldersRes.data.data || [];
        }

        if (promptsRes.data.status === 'ok') {
          this.currentPrompts = promptsRes.data.data || [];
        }

        // 更新面包屑
        this.updateBreadcrumb(folderId);
      } finally {
        this.loading = false;
      }
    },

    /**
     * 更新面包屑路径
     */
    updateBreadcrumb(folderId: string | null): void {
      if (folderId === null) {
        this.breadcrumbPath = [];
        return;
      }

      // 从树中查找路径
      const path: FolderTreeNode[] = [];
      const findPath = (nodes: FolderTreeNode[], targetId: string): boolean => {
        for (const node of nodes) {
          if (node.folder_id === targetId) {
            path.push(node);
            return true;
          }
          if (node.children.length > 0 && findPath(node.children, targetId)) {
            path.unshift(node);
            return true;
          }
        }
        return false;
      };

      findPath(this.folderTree, folderId);
      this.breadcrumbPath = path;
    },

    /**
     * 刷新当前文件夹内容
     */
    async refreshCurrentFolder(): Promise<void> {
      await this.navigateToFolder(this.currentFolderId);
    },

    /**
     * 移动 Prompt 到文件夹
     */
    async movePromptToFolder(
      promptId: string,
      targetFolderId: string | null,
    ): Promise<void> {
      const response = await promptApi.move(promptId, targetFolderId);

      if (response.data.status !== 'ok') {
        throw new Error(response.data.message || '移动提示词失败');
      }

      // 刷新当前文件夹内容和文件夹树
      await Promise.all([this.refreshCurrentFolder(), this.loadFolderTree()]);
    },

    /**
     * 移动文件夹到另一个文件夹
     */
    async moveFolderToFolder(
      folderId: string,
      targetParentId: string | null,
    ): Promise<void> {
      const response = await promptApi.updateFolder(folderId, {
        parent_id: targetParentId,
      });

      if (response.data.status !== 'ok') {
        throw new Error(response.data.message || '移动文件夹失败');
      }

      // 刷新当前文件夹内容和文件夹树
      await Promise.all([this.refreshCurrentFolder(), this.loadFolderTree()]);
    },

    /**
     * 创建文件夹
     */
    async createFolder(data: {
      name: string;
      parent_id?: string | null;
      description?: string;
    }): Promise<PromptFolder> {
      const response = await promptApi.createFolder({
        ...data,
        parent_id: data.parent_id ?? this.currentFolderId,
      });

      if (response.data.status !== 'ok') {
        throw new Error(response.data.message || '创建文件夹失败');
      }

      // 刷新当前文件夹内容和文件夹树
      await Promise.all([this.refreshCurrentFolder(), this.loadFolderTree()]);

      return response.data.data.folder as PromptFolder;
    },

    /**
     * 更新文件夹
     */
    async updateFolder(data: {
      folder_id: string;
      name?: string;
      description?: string;
    }): Promise<void> {
      const response = await promptApi.updateFolder(data.folder_id, data);

      if (response.data.status !== 'ok') {
        throw new Error(response.data.message || '更新文件夹失败');
      }

      // 刷新当前文件夹内容和文件夹树
      await Promise.all([this.refreshCurrentFolder(), this.loadFolderTree()]);
    },

    /**
     * 删除文件夹
     */
    async deleteFolder(folderId: string): Promise<void> {
      const deletedFolder = this.findFolderInTree(folderId);
      const isCurrentFolderDeleted =
        this.currentFolderId === folderId ||
        this.breadcrumbPath.some((folder) => folder.folder_id === folderId);
      const response = await promptApi.deleteFolder(folderId);

      if (response.data.status !== 'ok') {
        throw new Error(response.data.message || '删除文件夹失败');
      }

      // If the active folder was deleted, return to its parent instead of
      // keeping a stale folder ID that would hide moved prompts and folders.
      const targetFolderId = isCurrentFolderDeleted
        ? (deletedFolder?.parent_id ?? null)
        : this.currentFolderId;
      await this.loadFolderTree();
      await this.navigateToFolder(targetFolderId);
    },

    /**
     * 删除 Prompt
     */
    async deletePrompt(promptId: string): Promise<void> {
      const response = await promptApi.delete(promptId);

      if (response.data.status !== 'ok') {
        throw new Error(response.data.message || '删除提示词失败');
      }

      // 刷新当前文件夹内容
      await this.refreshCurrentFolder();
    },

    /**
     * 批量更新排序
     */
    async reorderItems(items: ReorderItem[]): Promise<void> {
      const response = await promptApi.reorder(items);

      if (response.data.status !== 'ok') {
        throw new Error(response.data.message || '更新排序失败');
      }

      // 刷新当前文件夹内容
      await this.refreshCurrentFolder();
    },

    /**
     * 根据文件夹 ID 查找树节点
     */
    findFolderInTree(folderId: string): FolderTreeNode | null {
      const findNode = (nodes: FolderTreeNode[]): FolderTreeNode | null => {
        for (const node of nodes) {
          if (node.folder_id === folderId) {
            return node;
          }
          if (node.children.length > 0) {
            const found = findNode(node.children);
            if (found) return found;
          }
        }
        return null;
      };
      return findNode(this.folderTree);
    },
  },
});
