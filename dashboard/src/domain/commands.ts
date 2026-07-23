/**
 * Command data returned by the Dashboard API.
 *
 * These contracts are shared by API clients and presentation components. They
 * deliberately do not include component state.
 */
export type CommandType = 'command' | 'group' | 'sub_command';

export type PermissionType = 'admin' | 'everyone' | 'member';

export interface CommandItem {
  handler_full_name: string;
  handler_name: string;
  plugin: string;
  plugin_display_name: string | null;
  module_path: string;
  description: string;
  type: CommandType;
  parent_signature: string;
  parent_group_handler: string;
  original_command: string;
  current_fragment: string;
  effective_command: string;
  signature: string;
  display_signature: string;
  aliases: string[];
  permission: PermissionType;
  enabled: boolean;
  is_group: boolean;
  has_conflict: boolean;
  reserved: boolean;
  sub_commands: CommandItem[];
}
