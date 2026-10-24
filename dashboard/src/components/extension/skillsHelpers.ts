export const STATUS_WAITING = 'waiting' as const;
export const STATUS_UPLOADING = 'uploading' as const;
export const STATUS_SUCCESS = 'success' as const;
export const STATUS_ERROR = 'error' as const;
export const STATUS_SKIPPED = 'skipped' as const;

export type UploadStatus =
  | typeof STATUS_WAITING
  | typeof STATUS_UPLOADING
  | typeof STATUS_SUCCESS
  | typeof STATUS_ERROR
  | typeof STATUS_SKIPPED;
export type SnackbarColor = 'success' | 'error' | 'warning';

export interface UploadItem {
  id: string;
  file: File;
  name: string;
  size: number;
  status: UploadStatus;
  validationMessage: string;
  filenameKey: string;
}

export interface UploadResultEntry {
  filename?: string;
  name?: string;
  error?: string;
}

export interface SkillEntry {
  type: string;
  path: string;
  name: string;
  editable: boolean;
  [key: string]: unknown;
}

export interface EditorDialogState {
  show: boolean;
  skillName: string;
  currentDir: string;
  entries: SkillEntry[];
  filePath: string;
  content: string;
  fileEditable: boolean;
  fileDirty: boolean;
  loadingFiles: boolean;
  loadingFile: boolean;
  saving: boolean;
  error: string;
}

export function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

export function getString(value: unknown) {
  return typeof value === 'string' ? value : '';
}

export function getBoolean(value: unknown, fallback = false) {
  return typeof value === 'boolean' ? value : fallback;
}

export function getNumber(value: unknown, fallback = 0) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

export function normalizeSkillEntry(value: unknown): SkillEntry | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }

  const path = getString(record.path).trim();
  const name = getString(record.name).trim();
  const type = getString(record.type).trim();
  if (!path || !name || !type) {
    return null;
  }

  return {
    ...record,
    path,
    name,
    type,
    editable: record.editable !== false,
  };
}

export function normalizeUploadName(name: string) {
  return String(name).trim().toLowerCase();
}

export function formatFileSize(size: number) {
  if (!Number.isFinite(size) || size <= 0) return '0 B';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function statusChipClass(status: UploadStatus) {
  return `skills-status-chip skills-status-chip--${status}`;
}
