import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  listProjects: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
}));

vi.mock('@/api/v1', () => ({ chatApi: api }));

const toast = vi.hoisted(() => ({
  toast: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
}));

vi.mock('@/utils/toast', () => ({ useToast: () => toast }));

import { useProjects } from '@/composables/useProjects';

describe('useProjects mutations', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    api.listProjects.mockResolvedValue({ data: { status: 'ok', data: [] } });
  });

  it('returns true and refreshes the list on success', async () => {
    api.createProject.mockResolvedValue({
      data: { status: 'ok', data: { project_id: 'p1' } },
    });

    const projects = useProjects();

    await expect(projects.createProject('demo')).resolves.toBe(true);
    expect(api.listProjects).toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('returns false and toasts the backend message on status error', async () => {
    api.updateProject.mockResolvedValue({
      data: { status: 'error', message: 'Project p1 not found' },
    });

    const projects = useProjects();

    await expect(projects.updateProject('p1', 'renamed')).resolves.toBe(false);
    expect(toast.error).toHaveBeenCalledWith('Project p1 not found');
    expect(api.listProjects).not.toHaveBeenCalled();
  });

  it('falls back to the localized message when status error has none', async () => {
    api.createProject.mockResolvedValue({ data: { status: 'error' } });

    const projects = useProjects();

    await expect(projects.createProject('demo')).resolves.toBe(false);
    expect(toast.error).toHaveBeenCalledWith('Failed to create project');
  });

  it('returns false and toasts a resolved error when the request rejects', async () => {
    api.deleteProject.mockRejectedValue(new Error('boom'));

    const projects = useProjects();
    projects.selectedProjectId.value = 'p1';

    await expect(projects.deleteProject('p1')).resolves.toBe(false);
    expect(toast.error).toHaveBeenCalledWith('boom');
    expect(projects.selectedProjectId.value).toBe('p1');
    expect(api.listProjects).not.toHaveBeenCalled();
  });

  it('clears the selected project only on a successful delete', async () => {
    api.deleteProject.mockResolvedValue({ data: { status: 'ok' } });

    const projects = useProjects();
    projects.selectedProjectId.value = 'p1';

    await expect(projects.deleteProject('p1')).resolves.toBe(true);
    expect(projects.selectedProjectId.value).toBeNull();
  });
});
