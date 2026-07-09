export interface SuggestionCommand {
  handler_full_name: string;
  effective_command: string;
  display_signature?: string;
  description: string;
  plugin_display_name: string | null;
  enabled: boolean;
  reserved: boolean;
}

export function buildSuggestionSignature(
  commandText: string,
  commandSignature: string,
  effectiveCommand: string,
) {
  if (!commandSignature) return commandText;
  if (commandSignature === effectiveCommand) return commandText;
  if (!commandSignature.startsWith(effectiveCommand)) return commandSignature;

  return `${commandText}${commandSignature.slice(effectiveCommand.length)}`;
}

export function rankSuggestionCommands(
  commands: SuggestionCommand[],
  query: string,
  normalizeText: (value: string) => string,
) {
  const normalizedQuery = normalizeText(query);
  if (!normalizedQuery) {
    return [...commands].sort(compareSuggestionCommands);
  }

  return commands
    .map((command) => {
      const commandText = normalizeText(command.effective_command);
      const pluginText = normalizeText(command.plugin_display_name || '');
      const descriptionText = normalizeText(command.description || '');
      const matchRank = getSuggestionMatchRank(
        normalizedQuery,
        commandText,
        pluginText,
        descriptionText,
      );
      if (matchRank === null) return null;

      return {
        command,
        matchRank,
        commandLength: commandText.length,
        signatureLength: (
          command.display_signature || command.effective_command
        ).length,
      };
    })
    .filter((item): item is NonNullable<typeof item> => item !== null)
    .sort((left, right) => {
      if (left.matchRank !== right.matchRank) {
        return left.matchRank - right.matchRank;
      }
      if (left.command.reserved !== right.command.reserved) {
        return Number(right.command.reserved) - Number(left.command.reserved);
      }
      if (left.signatureLength !== right.signatureLength) {
        return left.signatureLength - right.signatureLength;
      }
      if (left.commandLength !== right.commandLength) {
        return left.commandLength - right.commandLength;
      }
      return left.command.effective_command.localeCompare(
        right.command.effective_command,
      );
    })
    .map((item) => item.command);
}

function getSuggestionMatchRank(
  query: string,
  commandText: string,
  pluginText: string,
  descriptionText: string,
) {
  if (commandText === query) return 0;
  if (commandText.startsWith(query)) return 1;
  if (commandText.includes(query)) return 2;
  if (pluginText.startsWith(query)) return 3;
  if (pluginText.includes(query)) return 4;
  if (descriptionText.includes(query)) return 5;
  return null;
}

function compareSuggestionCommands(
  left: SuggestionCommand,
  right: SuggestionCommand,
) {
  if (left.reserved !== right.reserved) {
    return Number(right.reserved) - Number(left.reserved);
  }

  const leftSignatureLength = (left.display_signature || left.effective_command)
    .length;
  const rightSignatureLength = (
    right.display_signature || right.effective_command
  ).length;
  if (leftSignatureLength !== rightSignatureLength) {
    return leftSignatureLength - rightSignatureLength;
  }

  const leftCommandLength = left.effective_command.length;
  const rightCommandLength = right.effective_command.length;
  if (leftCommandLength !== rightCommandLength) {
    return leftCommandLength - rightCommandLength;
  }

  return left.effective_command.localeCompare(right.effective_command);
}
