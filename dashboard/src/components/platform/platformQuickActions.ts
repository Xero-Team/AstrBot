export const QUICK_ACTION_ORDER = [
  'send_poke',
  'send_like',
  'send_group_notice',
  'set_group_admin',
  'set_group_ban',
  'set_group_card',
  'kick_group_member',
  'kick_group_members',
  'leave_group',
  'set_group_whole_ban',
  'set_essence_message',
  'delete_essence_message',
] as const;

export type QuickActionName = (typeof QUICK_ACTION_ORDER)[number];
export type QuickActionCategory =
  'all' | 'social' | 'group_management' | 'announcement' | 'message';
export type QuickActionFieldKind =
  'text' | 'textarea' | 'number' | 'boolean' | 'string-list';

export interface QuickActionFieldDefinition {
  key: string;
  kind: QuickActionFieldKind;
  label: string;
  hint?: string;
  placeholder?: string;
  defaultValue?: string | number | boolean;
}

export interface QuickActionDefinition {
  category: Exclude<QuickActionCategory, 'all'>;
  help?: string;
  fields: QuickActionFieldDefinition[];
}

type Translate = (key: string) => string;

export function buildQuickActionDefinitions(
  tm: Translate,
): Record<QuickActionName, QuickActionDefinition> {
  return {
    send_poke: {
      category: 'social',
      help: tm('quickActions.help.send_poke'),
      fields: [
        {
          key: 'user_id',
          kind: 'text',
          label: tm('quickActions.fields.user_id'),
        },
        {
          key: 'group_id',
          kind: 'text',
          label: tm('quickActions.fields.group_id'),
          hint: tm('quickActions.fields.group_idHintOptional'),
        },
        {
          key: 'target_id',
          kind: 'text',
          label: tm('quickActions.fields.target_id'),
          hint: tm('quickActions.fields.target_idHintOptional'),
        },
      ],
    },
    send_like: {
      category: 'social',
      help: tm('quickActions.help.send_like'),
      fields: [
        {
          key: 'user_id',
          kind: 'text',
          label: tm('quickActions.fields.user_id'),
        },
        {
          key: 'times',
          kind: 'number',
          label: tm('quickActions.fields.times'),
          defaultValue: 1,
        },
      ],
    },
    send_group_notice: {
      category: 'announcement',
      help: tm('quickActions.help.send_group_notice'),
      fields: [
        {
          key: 'group_id',
          kind: 'text',
          label: tm('quickActions.fields.group_id'),
        },
        {
          key: 'content',
          kind: 'textarea',
          label: tm('quickActions.fields.content'),
        },
        {
          key: 'image',
          kind: 'text',
          label: tm('quickActions.fields.image'),
          hint: tm('quickActions.fields.imageHintOptional'),
        },
        {
          key: 'pinned',
          kind: 'number',
          label: tm('quickActions.fields.pinned'),
        },
      ],
    },
    set_group_admin: {
      category: 'group_management',
      fields: [
        {
          key: 'group_id',
          kind: 'text',
          label: tm('quickActions.fields.group_id'),
        },
        {
          key: 'user_id',
          kind: 'text',
          label: tm('quickActions.fields.user_id'),
        },
        {
          key: 'enable',
          kind: 'boolean',
          label: tm('quickActions.fields.enable'),
          defaultValue: true,
        },
      ],
    },
    set_group_ban: {
      category: 'group_management',
      fields: [
        {
          key: 'group_id',
          kind: 'text',
          label: tm('quickActions.fields.group_id'),
        },
        {
          key: 'user_id',
          kind: 'text',
          label: tm('quickActions.fields.user_id'),
        },
        {
          key: 'duration',
          kind: 'number',
          label: tm('quickActions.fields.duration'),
          defaultValue: 60,
        },
      ],
    },
    set_group_card: {
      category: 'group_management',
      fields: [
        {
          key: 'group_id',
          kind: 'text',
          label: tm('quickActions.fields.group_id'),
        },
        {
          key: 'user_id',
          kind: 'text',
          label: tm('quickActions.fields.user_id'),
        },
        {
          key: 'card',
          kind: 'text',
          label: tm('quickActions.fields.card'),
        },
      ],
    },
    kick_group_member: {
      category: 'group_management',
      fields: [
        {
          key: 'group_id',
          kind: 'text',
          label: tm('quickActions.fields.group_id'),
        },
        {
          key: 'user_id',
          kind: 'text',
          label: tm('quickActions.fields.user_id'),
        },
        {
          key: 'reject_add_request',
          kind: 'boolean',
          label: tm('quickActions.fields.reject_add_request'),
          defaultValue: false,
        },
      ],
    },
    kick_group_members: {
      category: 'group_management',
      help: tm('quickActions.help.kick_group_members'),
      fields: [
        {
          key: 'group_id',
          kind: 'text',
          label: tm('quickActions.fields.group_id'),
        },
        {
          key: 'user_ids',
          kind: 'string-list',
          label: tm('quickActions.fields.user_ids'),
          hint: tm('quickActions.fields.user_idsHint'),
        },
        {
          key: 'reject_add_request',
          kind: 'boolean',
          label: tm('quickActions.fields.reject_add_request'),
          defaultValue: false,
        },
      ],
    },
    leave_group: {
      category: 'group_management',
      fields: [
        {
          key: 'group_id',
          kind: 'text',
          label: tm('quickActions.fields.group_id'),
        },
        {
          key: 'is_dismiss',
          kind: 'boolean',
          label: tm('quickActions.fields.is_dismiss'),
          defaultValue: false,
        },
      ],
    },
    set_group_whole_ban: {
      category: 'group_management',
      fields: [
        {
          key: 'group_id',
          kind: 'text',
          label: tm('quickActions.fields.group_id'),
        },
        {
          key: 'enable',
          kind: 'boolean',
          label: tm('quickActions.fields.enable'),
          defaultValue: true,
        },
      ],
    },
    set_essence_message: {
      category: 'message',
      fields: [
        {
          key: 'message_id',
          kind: 'text',
          label: tm('quickActions.fields.message_id'),
        },
      ],
    },
    delete_essence_message: {
      category: 'message',
      help: tm('quickActions.help.delete_essence_message'),
      fields: [
        {
          key: 'message_id',
          kind: 'text',
          label: tm('quickActions.fields.message_id'),
          hint: tm('quickActions.fields.messageIdHintOptional'),
        },
        {
          key: 'group_id',
          kind: 'text',
          label: tm('quickActions.fields.group_id'),
          hint: tm('quickActions.fields.group_idHintOptional'),
        },
        {
          key: 'msg_seq',
          kind: 'text',
          label: tm('quickActions.fields.msg_seq'),
          hint: tm('quickActions.fields.msgSeqHintOptional'),
        },
        {
          key: 'msg_random',
          kind: 'text',
          label: tm('quickActions.fields.msg_random'),
          hint: tm('quickActions.fields.msgRandomHintOptional'),
        },
      ],
    },
  };
}

export function getQuickActionableActions(
  supportedActions: string[],
): QuickActionName[] {
  return QUICK_ACTION_ORDER.filter((action) =>
    supportedActions.includes(action),
  );
}
