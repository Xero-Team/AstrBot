import { generatedOptions, openApiV1, typed } from './shared';
import type { AxiosRequestConfig } from './shared';

/** The CLIs AstrBot knows how to write a global configuration for. */
export type CodingCliKind = 'claude_code' | 'codex';

/** One provider the operator configured for a CLI. */
export interface CodingCliProvider {
  id: string;
  name: string;
  base_url: string;
  model: string;
  note: string;
  /** A key is reported as present, never as its value. */
  has_api_key: boolean;
  /** Whether the CLI's own file currently holds this provider. */
  current: boolean;
}

/** One CLI's own configuration file, plus what it can be switched to. */
export interface CodingCliState {
  cli: CodingCliKind;
  path: string;
  exists: boolean;
  managed: boolean;
  backed_up: boolean;
  base_url: string;
  model: string;
  has_credential: boolean;
  providers: CodingCliProvider[];
}

/**
 * One provider as `btw.cli_providers` stores it.
 *
 * `api_key` is what the operator typed in the field and nothing else.  A config
 * response writes the marker `__ASTRBOT_REDACTED__` where a stored key would
 * be, so the editor treats it as "a key is stored, the field is empty": the
 * marker goes back only for the entry it came from, and only a switch ever
 * writes a value into the CLI's own file.
 */
export interface StoredCliProvider extends CodingCliProvider {
  /** The CLI this provider is scoped to; empty means either CLI may use it. */
  cli: string;
  api_key: string;
}

export interface CodingCliStatePayload {
  clis: CodingCliState[];
}

export const codingCliApi = {
  /**
   * Read each CLI's own configuration.
   *
   * A request config is optional and carries the step-up credential when the
   * backend asks for one: the read is an ordinary permission, but an operator
   * whose session has not proved itself yet still has to answer the challenge
   * before the list can be filled in.
   */
  state(requestConfig?: AxiosRequestConfig) {
    return typed<CodingCliStatePayload>(
      openApiV1.getCodingCliGlobalConfig(generatedOptions({}, requestConfig)),
    );
  },
  switchProvider(
    payload: { cli: CodingCliKind; provider_id: string },
    requestConfig?: AxiosRequestConfig,
  ) {
    return typed<CodingCliState>(
      openApiV1.switchCodingCliProvider(
        generatedOptions(
          {
            body: { cli: payload.cli, provider_id: payload.provider_id },
          },
          requestConfig,
        ),
      ),
    );
  },
  remove(cli: CodingCliKind, requestConfig?: AxiosRequestConfig) {
    return typed<CodingCliState>(
      openApiV1.removeCodingCliGlobalConfig(
        generatedOptions({ path: { cli } }, requestConfig),
      ),
    );
  },
};
