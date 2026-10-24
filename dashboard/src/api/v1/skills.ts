import { openApiV1, typed } from './shared';
import type { OpenConfig, SkillListData } from './types';

export const skillApi = {
  list(params?: { enabled?: boolean; source?: string }) {
    return typed<SkillListData>(openApiV1.listSkills({ query: params }));
  },
  uploadBatch(files: File[]) {
    return typed<OpenConfig>(openApiV1.uploadSkillsBatch({ body: { files } }));
  },
  setEnabled(skillName: string, enabled: boolean) {
    return typed<OpenConfig>(
      openApiV1.updateSkill({
        path: { skill_name: skillName },
        body: { active: enabled },
      }),
    );
  },
  delete(skillName: string) {
    return typed<OpenConfig>(
      openApiV1.deleteSkill({ path: { skill_name: skillName } }),
    );
  },
  download(skillName: string) {
    return openApiV1.downloadSkill({
      path: { skill_name: skillName },
      responseType: 'blob',
    });
  },
  listFiles(skillName: string, path = '') {
    return typed<OpenConfig>(
      openApiV1.listSkillFiles({
        path: { skill_name: skillName },
        query: path ? { path } : undefined,
      }),
    );
  },
  getFile(skillName: string, path: string) {
    return typed<OpenConfig>(
      openApiV1.getSkillFile({
        path: { skill_name: skillName, file_path: path },
      }),
    );
  },
  updateFile(skillName: string, path: string, content: string) {
    return typed<OpenConfig>(
      openApiV1.updateSkillFile({
        path: { skill_name: skillName, file_path: path },
        body: content,
      }),
    );
  },
};
