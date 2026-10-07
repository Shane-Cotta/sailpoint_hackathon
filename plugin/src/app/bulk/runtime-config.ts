/**
 * The plugin's runtime config: public/bulk-access.config.json.
 *
 * plugin/install.py writes it from the tenant config (config/<tenant>.json), so
 * the same bundle works in any tenant. Nothing tenant-specific is compiled in.
 * The committed copy holds neutral defaults.
 */
export type ItemType = 'ACCESS_PROFILE' | 'ROLE' | 'ENTITLEMENT';

export const ITEM_TYPES: readonly ItemType[] = ['ACCESS_PROFILE', 'ROLE', 'ENTITLEMENT'];

export interface RuntimeConfig {
  /** Names every object install.py created, e.g. "ACME". */
  prefix: string;
  /** "dry-run" (approve, but request nothing) or "live". */
  mode: 'dry-run' | 'live';
  /** The plugin workflow, found by name when workflowId is empty. */
  workflowName: string;
  workflowId: string | null;
  incPattern: string;
  incMessage: string;
  incExample: string;
  peopleMax: number;
  itemsMax: number;
  catalogTypes: ItemType[];
  nameStartsWith: string | null;
  /** Shown in the banner: where people without ORG_ADMIN should go instead. */
  launcherName: string;
}

export const DEFAULT_CONFIG: RuntimeConfig = {
  prefix: '',
  mode: 'dry-run',
  workflowName: 'Bulk Access Request (Plugin)',
  workflowId: null,
  incPattern: '^INC\\d{7}$',
  incMessage: 'Enter a ServiceNow incident number: INC followed by 7 digits, e.g. INC0012345.',
  incExample: 'INC0012345',
  peopleMax: 50,
  itemsMax: 25,
  catalogTypes: [...ITEM_TYPES],
  nameStartsWith: null,
  launcherName: 'Bulk Access Request',
};

export class RuntimeConfigError extends Error {}

/** Merge a parsed JSON object over the defaults, rejecting values that would break the page. */
export function parseRuntimeConfig(raw: unknown): RuntimeConfig {
  const data = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const cfg: RuntimeConfig = { ...DEFAULT_CONFIG };
  const str = (key: keyof RuntimeConfig) => {
    const v = data[key];
    return typeof v === 'string' ? v : undefined;
  };
  const num = (key: keyof RuntimeConfig) => {
    const v = data[key];
    return typeof v === 'number' && Number.isFinite(v) ? v : undefined;
  };

  cfg.prefix = str('prefix') ?? cfg.prefix;
  cfg.mode = data['mode'] === 'live' ? 'live' : 'dry-run';
  cfg.workflowName = str('workflowName') || cfg.workflowName;
  cfg.workflowId = str('workflowId') || null;
  cfg.incPattern = str('incPattern') || cfg.incPattern;
  cfg.incMessage = str('incMessage') || cfg.incMessage;
  cfg.incExample = str('incExample') || cfg.incExample;
  cfg.peopleMax = num('peopleMax') ?? cfg.peopleMax;
  cfg.itemsMax = num('itemsMax') ?? cfg.itemsMax;
  cfg.nameStartsWith = str('nameStartsWith') || null;
  cfg.launcherName = str('launcherName') || cfg.launcherName;
  const types = Array.isArray(data['catalogTypes']) ? (data['catalogTypes'] as unknown[]) : null;
  if (types) {
    const bad = types.filter((t) => !ITEM_TYPES.includes(t as ItemType));
    if (bad.length) {
      throw new RuntimeConfigError(`catalogTypes may only contain ${ITEM_TYPES.join(', ')} (got ${bad.join(', ')}).`);
    }
    cfg.catalogTypes = types as ItemType[];
  }

  try {
    new RegExp(cfg.incPattern);
  } catch {
    throw new RuntimeConfigError(`incPattern is not a valid regular expression: ${cfg.incPattern}`);
  }
  if (!new RegExp(cfg.incPattern).test(cfg.incExample)) {
    throw new RuntimeConfigError(`incExample (${cfg.incExample}) does not match incPattern.`);
  }
  if (cfg.itemsMax < 1 || cfg.itemsMax > 25) {
    throw new RuntimeConfigError('itemsMax must be between 1 and 25 (SailPoint\'s per-request limit).');
  }
  if (cfg.peopleMax < 1 || cfg.peopleMax > 250) {
    throw new RuntimeConfigError('peopleMax must be between 1 and 250.');
  }
  return cfg;
}

/** Fetch the config shipped next to index.html (relative URL: the bundle is served from a CDN path). */
export async function loadRuntimeConfig(fetchFn: typeof fetch = fetch): Promise<RuntimeConfig> {
  const resp = await fetchFn('bulk-access.config.json', { cache: 'no-store' });
  if (!resp.ok) {
    throw new RuntimeConfigError(`Could not load bulk-access.config.json (HTTP ${resp.status}). Run plugin/install.py.`);
  }
  return parseRuntimeConfig(await resp.json());
}
