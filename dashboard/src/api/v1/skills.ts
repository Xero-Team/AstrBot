import { openApiV1, typed } from './shared';
import type {
  NeoCandidateActionRequest,
  NeoReleaseActionRequest,
} from './shared';
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
  neoCandidates(params?: { skill_key?: string; status?: string }) {
    return typed<OpenConfig>(
      openApiV1.listNeoSkillCandidates({ query: params }),
    );
  },
  neoReleases(params?: { skill_key?: string; stage?: string }) {
    return typed<OpenConfig>(openApiV1.listNeoSkillReleases({ query: params }));
  },
  neoPayload(payloadRef: string) {
    return typed<OpenConfig>(
      openApiV1.getNeoSkillPayload({ query: { payload_ref: payloadRef } }),
    );
  },
  evaluateNeoCandidate(body: NeoCandidateActionRequest) {
    return typed<OpenConfig>(openApiV1.evaluateNeoSkillCandidate({ body }));
  },
  promoteNeoCandidate(body: NeoCandidateActionRequest) {
    return typed<OpenConfig>(openApiV1.promoteNeoSkillCandidate({ body }));
  },
  rollbackNeoRelease(body: NeoReleaseActionRequest) {
    return typed<OpenConfig>(openApiV1.rollbackNeoSkillRelease({ body }));
  },
  syncNeoRelease(body: NeoReleaseActionRequest) {
    return typed<OpenConfig>(openApiV1.syncNeoSkillRelease({ body }));
  },
  deleteNeoCandidate(body: NeoCandidateActionRequest) {
    return typed<OpenConfig>(openApiV1.deleteNeoSkillCandidate({ body }));
  },
  deleteNeoRelease(body: NeoReleaseActionRequest) {
    return typed<OpenConfig>(openApiV1.deleteNeoSkillRelease({ body }));
  },
};
