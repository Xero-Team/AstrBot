import { openApiV1, typed } from './shared';
import type {
  PersonaFolderRequest,
  PersonaMoveRequest,
  PersonaRequest,
  ReorderRequest,
} from './shared';
import type {
  OpenConfig,
  PersonaData,
  PersonaFolderData,
  PersonaFolderInput,
  PersonaInput,
} from './types';

export const personaApi = {
  tree() {
    return typed<PersonaFolderData[]>(openApiV1.getPersonaTree());
  },
  folders(parentId?: string | null) {
    return typed<PersonaFolderData[]>(
      openApiV1.listPersonaFolders({
        query:
          parentId === undefined ? undefined : { parent_id: parentId ?? '' },
      }),
    );
  },
  createFolder(folder: PersonaFolderInput) {
    return typed<OpenConfig>(
      openApiV1.createPersonaFolder({
        body: folder as unknown as PersonaFolderRequest,
      }),
    );
  },
  updateFolder(folderId: string, folder: PersonaFolderInput) {
    return typed<OpenConfig>(
      openApiV1.updatePersonaFolder({
        path: { folder_id: folderId },
        body: folder as unknown as PersonaFolderRequest,
      }),
    );
  },
  deleteFolder(folderId: string) {
    return typed<OpenConfig>(
      openApiV1.deletePersonaFolder({ path: { folder_id: folderId } }),
    );
  },
  list(folderId?: string | null) {
    return typed<PersonaData[]>(
      openApiV1.listPersonas({
        query:
          folderId === undefined ? undefined : { folder_id: folderId ?? '' },
      }),
    );
  },
  get(personaId: string) {
    return typed<PersonaData>(
      openApiV1.getPersona({ path: { persona_id: personaId } }),
    );
  },
  create(persona: PersonaInput) {
    return typed<OpenConfig>(
      openApiV1.createPersona({ body: persona as unknown as PersonaRequest }),
    );
  },
  update(personaId: string, persona: Omit<PersonaInput, 'persona_id'>) {
    return typed<OpenConfig>(
      openApiV1.updatePersona({
        path: { persona_id: personaId },
        body: persona as unknown as PersonaRequest,
      }),
    );
  },
  delete(personaId: string) {
    return typed<OpenConfig>(
      openApiV1.deletePersona({ path: { persona_id: personaId } }),
    );
  },
  move(personaId: string, folderId: string | null) {
    const payload: PersonaMoveRequest = {
      persona_id: personaId,
      folder_id: folderId ?? undefined,
    };
    return typed<OpenConfig>(openApiV1.movePersonaItem({ body: payload }));
  },
  reorder(items: ReorderRequest['items']) {
    return typed<OpenConfig>(
      openApiV1.reorderPersonaItems({ body: { items } }),
    );
  },
};
