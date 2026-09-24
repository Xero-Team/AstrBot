import { openApiV1, typed } from './shared';
import type {
  PromptFolderRequest,
  PromptMoveRequest,
  PromptRequest,
  ReorderRequest,
} from './shared';
import type {
  OpenConfig,
  PromptData,
  PromptFolderData,
  PromptFolderInput,
  PromptInput,
} from './types';

export const promptApi = {
  tree() {
    return typed<PromptFolderData[]>(openApiV1.getPromptTree());
  },
  folders(parentId?: string | null) {
    return typed<PromptFolderData[]>(
      openApiV1.listPromptFolders({
        query:
          parentId === undefined ? undefined : { parent_id: parentId ?? '' },
      }),
    );
  },
  createFolder(folder: PromptFolderInput) {
    return typed<OpenConfig>(
      openApiV1.createPromptFolder({
        body: folder as unknown as PromptFolderRequest,
      }),
    );
  },
  updateFolder(folderId: string, folder: PromptFolderInput) {
    return typed<OpenConfig>(
      openApiV1.updatePromptFolder({
        path: { folder_id: folderId },
        body: folder as unknown as PromptFolderRequest,
      }),
    );
  },
  deleteFolder(folderId: string) {
    return typed<OpenConfig>(
      openApiV1.deletePromptFolder({ path: { folder_id: folderId } }),
    );
  },
  list(folderId?: string | null) {
    return typed<PromptData[]>(
      openApiV1.listPrompts({
        query:
          folderId === undefined ? undefined : { folder_id: folderId ?? '' },
      }),
    );
  },
  get(promptId: string) {
    return typed<PromptData>(
      openApiV1.getPrompt({ path: { prompt_id: promptId } }),
    );
  },
  create(prompt: PromptInput) {
    return typed<OpenConfig>(
      openApiV1.createPrompt({ body: prompt as unknown as PromptRequest }),
    );
  },
  update(promptId: string, prompt: Omit<PromptInput, 'prompt_id'>) {
    return typed<OpenConfig>(
      openApiV1.updatePrompt({
        path: { prompt_id: promptId },
        body: prompt as unknown as PromptRequest,
      }),
    );
  },
  delete(promptId: string) {
    return typed<OpenConfig>(
      openApiV1.deletePrompt({ path: { prompt_id: promptId } }),
    );
  },
  move(promptId: string, folderId: string | null) {
    const payload: PromptMoveRequest = {
      prompt_id: promptId,
      folder_id: folderId ?? undefined,
    };
    return typed<OpenConfig>(openApiV1.movePromptItem({ body: payload }));
  },
  reorder(items: ReorderRequest['items']) {
    return typed<OpenConfig>(openApiV1.reorderPromptItems({ body: { items } }));
  },
};
