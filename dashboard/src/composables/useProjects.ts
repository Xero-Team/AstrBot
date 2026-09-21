import { ref } from 'vue';
import { chatApi } from '@/api/v1';
import type { Project } from '@/components/chat/ProjectList.vue';
import { useModuleI18n } from '@/i18n/composables';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { useToast } from '@/utils/toast';

interface MutationResponse {
  data: { status: string; message?: string | null };
}

export function useProjects() {
  const projects = ref<Project[]>([]);
  const selectedProjectId = ref<string | null>(null);
  const toast = useToast();
  const { tm } = useModuleI18n('features/chat');

  async function getProjects() {
    try {
      const res = await chatApi.listProjects();
      if (res.data.status === 'ok') {
        projects.value = res.data.data || [];
      }
    } catch (error) {
      console.error('Failed to fetch projects:', error);
    }
  }

  async function mutate(
    action: () => Promise<MutationResponse>,
    fallbackMessage: string,
  ): Promise<boolean> {
    try {
      const res = await action();
      if (res.data.status !== 'ok') {
        toast.error(res.data.message || fallbackMessage);
        return false;
      }
      await getProjects();
      return true;
    } catch (error) {
      console.error(fallbackMessage, error);
      toast.error(resolveErrorMessage(error, fallbackMessage));
      return false;
    }
  }

  async function createProject(
    title: string,
    emoji?: string,
    description?: string,
  ): Promise<boolean> {
    return mutate(
      () => chatApi.createProject({ title, emoji: emoji || '📁', description }),
      tm('project.createFailed'),
    );
  }

  async function updateProject(
    projectId: string,
    title?: string,
    emoji?: string,
    description?: string,
  ): Promise<boolean> {
    return mutate(
      () => chatApi.updateProject(projectId, { title, emoji, description }),
      tm('project.updateFailed'),
    );
  }

  async function deleteProject(projectId: string): Promise<boolean> {
    const ok = await mutate(
      () => chatApi.deleteProject(projectId),
      tm('project.deleteFailed'),
    );
    if (ok && selectedProjectId.value === projectId) {
      selectedProjectId.value = null;
    }
    return ok;
  }

  async function addSessionToProject(sessionId: string, projectId: string) {
    try {
      const res = await chatApi.addProjectSession(projectId, sessionId);
      return res.data.status === 'ok';
    } catch (error) {
      console.error('Failed to add session to project:', error);
      return false;
    }
  }

  async function removeSessionFromProject(sessionId: string) {
    try {
      const res = await chatApi.removeProjectSession(sessionId);
      return res.data.status === 'ok';
    } catch (error) {
      console.error('Failed to remove session from project:', error);
      return false;
    }
  }

  async function getProjectSessions(projectId: string) {
    try {
      const res = await chatApi.listProjectSessions(projectId);
      if (res.data.status === 'ok') {
        return res.data.data || [];
      }
      return [];
    } catch (error) {
      console.error('Failed to fetch project sessions:', error);
      return [];
    }
  }

  return {
    projects,
    selectedProjectId,
    getProjects,
    createProject,
    updateProject,
    deleteProject,
    addSessionToProject,
    removeSessionFromProject,
    getProjectSessions,
  };
}
