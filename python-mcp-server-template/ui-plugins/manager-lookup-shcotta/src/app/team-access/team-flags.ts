/**
 * Team access review flags -- a TypeScript port of the MCP server's
 * `sailpoint_mcp/tools/_team.py`.
 *
 * Python is the reference. Both implementations are held to the same contract,
 * `shared/team-flag-cases.json` (regenerate with `shared/make_flag_cases.py`),
 * so the Team Access Radar page and the chat tools always flag the same people
 * for the same reasons. Port rule changes here rule for rule, wording included.
 *
 * Input is identity documents from the Search API (`POST /v3/search`, index
 * `identities`, `includeNested: true`).
 */

export type Severity = 'high' | 'medium' | 'low';
export type FlagType =
  | 'leaver_risk'
  | 'privileged_access'
  | 'unique_access'
  | 'access_outlier'
  | 'missing_baseline'
  | 'no_roles';

export interface Flag {
  severity: Severity;
  type: FlagType;
  identity: string;
  reason: string;
  items?: string[];
}

export interface AccessSummary {
  roles: string[];
  access_profiles: string[];
  entitlements: string[];
  privileged: string[];
  accounts: Record<string, number>;
  disabled_accounts: number;
}

export interface Member {
  id: string | undefined;
  name: string;
  email?: string;
  job_title?: string;
  department?: string;
  lifecycle_state?: string;
  inactive: boolean;
  access_count: number;
  access: AccessSummary;
}

export interface BaselineItem {
  access: string;
  kind: AccessKind;
  held_by: number;
}

type AccessKind = 'roles' | 'access_profiles' | 'entitlements';
/** A search document: loosely typed on purpose, like the Python dicts. */
export type SearchDocument = Record<string, unknown>;

export const MIN_TEAM_FOR_PEER_FLAGS = 3;
export const OUTLIER_FACTOR = 1.5;
export const OUTLIER_MIN_GAP = 3;
export const BASELINE_SHARE = 0.8;
const MAX_ITEMS_PER_FLAG = 5;
const LEAVER_MARKERS = ['inactive', 'terminat', 'leaver', 'disabled', 'separated'];
const ACCESS_KINDS: Record<string, AccessKind> = {
  ROLE: 'roles',
  ACCESS_PROFILE: 'access_profiles',
  ENTITLEMENT: 'entitlements',
};
const KIND_ORDER: AccessKind[] = ['roles', 'access_profiles', 'entitlements'];
const SEVERITY_ORDER: Record<Severity, number> = { high: 0, medium: 1, low: 2 };

/** The Search API fields the review needs (same projection as TEAM_FIELDS in Python). */
export const TEAM_FIELDS = [
  'id', 'name', 'displayName', 'firstName', 'lastName', 'email', 'created',
  'lifecycleState', 'identityStatus', 'isManager', 'inactive',
  'manager.name', 'manager.displayName',
  'attributes.department', 'attributes.jobTitle', 'attributes.cloudLifecycleState',
  'source.name', 'accounts.source.name',
  'accessCount', 'entitlementCount', 'roleCount', 'accessProfileCount',
  'access.id', 'access.type', 'access.name', 'access.displayName', 'access.privileged', 'access.source.name',
  'accounts.id', 'accounts.name', 'accounts.disabled', 'accounts.privileged',
];

/** Python's sorted() order for strings: by code point, not locale. */
function byCodePoint(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

function sortedStrings(values: Iterable<string>): string[] {
  return [...values].sort(byCodePoint);
}

function get(doc: unknown, path: string): unknown {
  let current: unknown = doc;
  for (const part of path.split('.')) {
    if (current && typeof current === 'object' && !Array.isArray(current)) {
      current = (current as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
    if (current === null || current === undefined) {
      return undefined;
    }
  }
  return current;
}

function str(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

/** Python's `'{:g}'.format(x)` for the numbers we print (team medians). */
function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(6)));
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** Human-readable name for an access item: entitlements carry their source. */
export function accessLabel(item: Record<string, unknown>): string {
  const name = str(item['displayName']) ?? str(item['name']) ?? str(item['id']) ?? '?';
  if (item['type'] === 'ENTITLEMENT') {
    const source = str(get(item, 'source.name'));
    if (source) {
      return `${source}: ${name}`;
    }
  }
  return name;
}

export function summarizeAccess(doc: SearchDocument): AccessSummary {
  const grouped: Record<AccessKind, Set<string>> = {
    roles: new Set(),
    access_profiles: new Set(),
    entitlements: new Set(),
  };
  const privileged = new Set<string>();

  for (const item of (doc['access'] as unknown[]) ?? []) {
    if (!isRecord(item)) continue;
    const kind = ACCESS_KINDS[String(item['type'] ?? '').toUpperCase()];
    if (!kind) continue;
    const label = accessLabel(item);
    grouped[kind].add(label);
    if (item['privileged']) privileged.add(label);
  }

  const accounts = new Map<string, number>();
  let disabled = 0;
  for (const account of (doc['accounts'] as unknown[]) ?? []) {
    if (!isRecord(account)) continue;
    const source = str(get(account, 'source.name')) ?? 'Unknown source';
    accounts.set(source, (accounts.get(source) ?? 0) + 1);
    if (account['disabled']) disabled += 1;
    if (account['privileged']) {
      privileged.add(`${source} account: ${str(account['name']) ?? str(account['id'])}`);
    }
  }

  return {
    roles: sortedStrings(grouped.roles),
    access_profiles: sortedStrings(grouped.access_profiles),
    entitlements: sortedStrings(grouped.entitlements),
    privileged: sortedStrings(privileged),
    accounts: Object.fromEntries(sortedStrings(accounts.keys()).map((k) => [k, accounts.get(k)!])),
    disabled_accounts: disabled,
  };
}

export function buildMember(doc: SearchDocument): Member {
  const access = summarizeAccess(doc);
  const count = doc['accessCount'];
  return {
    id: str(doc['id']),
    name: str(doc['displayName']) ?? str(doc['name']) ?? str(doc['id']) ?? '?',
    email: str(doc['email']),
    job_title: str(get(doc, 'attributes.jobTitle')),
    department: str(get(doc, 'attributes.department')),
    lifecycle_state: str(doc['lifecycleState']) ?? str(get(doc, 'attributes.cloudLifecycleState')),
    inactive: !!doc['inactive'],
    access_count:
      typeof count === 'number'
        ? count
        : access.roles.length + access.access_profiles.length + access.entitlements.length,
    access,
  };
}

export function isLeaver(member: Member): boolean {
  if (member.inactive) return true;
  const state = (member.lifecycle_state ?? '').toLowerCase();
  return LEAVER_MARKERS.some((marker) => state.includes(marker));
}

function accessKeys(member: Member): Set<string> {
  const keys = new Set<string>();
  for (const kind of KIND_ORDER) {
    for (const label of member.access[kind]) keys.add(`${kind}|${label}`);
  }
  return keys;
}

function labelOf(key: string): string {
  return key.slice(key.indexOf('|') + 1);
}

/** Access items held by at least half the team -- the team's baseline. */
export function commonAccess(members: Member[], top = 10): BaselineItem[] {
  if (!members.length) return [];
  const counts = new Map<string, number>();
  for (const member of members) {
    for (const key of accessKeys(member)) counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const threshold = Math.max(2, Math.floor((members.length + 1) / 2));
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || byCodePoint(a[0], b[0]))
    .filter(([, n]) => n >= threshold)
    .slice(0, top)
    .map(([key, n]) => ({
      access: labelOf(key),
      kind: key.slice(0, key.indexOf('|')) as AccessKind,
      held_by: n,
    }));
}

/**
 * Deterministic, explainable review signals, most urgent first. See
 * `team_flags()` in `_team.py` for the rule descriptions.
 */
export function teamFlags(members: Member[]): Flag[] {
  const flags: Flag[] = [];
  const peerRules = members.length >= MIN_TEAM_FOR_PEER_FLAGS;

  const holders = new Map<string, number>();
  for (const member of members) {
    for (const key of accessKeys(member)) holders.set(key, (holders.get(key) ?? 0) + 1);
  }

  const counts = members.map((m) => m.access_count).filter((c) => Number.isInteger(c));
  const teamMedian = counts.length ? median(counts) : 0;

  const baseline = new Set(
    peerRules
      ? [...holders.entries()]
          .filter(([, n]) => n >= BASELINE_SHARE * members.length)
          .map(([key]) => key)
      : [],
  );
  const teamUsesRoles =
    members.filter((m) => m.access.roles.length > 0).length * 2 >= members.length;

  for (const member of members) {
    const name = member.name ?? member.id;
    const access = member.access;
    const total = member.access_count || 0;
    const nAccounts = Object.values(access.accounts).reduce((sum, n) => sum + n, 0);
    const keys = accessKeys(member);
    const unique = sortedStrings([...keys].filter((key) => holders.get(key) === 1).map(labelOf));

    if (isLeaver(member) && (total || nAccounts)) {
      flags.push({
        severity: 'high',
        type: 'leaver_risk',
        identity: name,
        reason:
          `Lifecycle state is ${member.lifecycle_state || 'inactive'} ` +
          `but still holds ${total} access item(s) and ${nAccounts} account(s).`,
      });
    }

    if (access.privileged.length) {
      const uniqueSet = new Set(unique);
      const privilegedUnique = peerRules
        ? sortedStrings(access.privileged.filter((label) => uniqueSet.has(label)))
        : [];
      let reason = `Holds ${access.privileged.length} privileged item(s)`;
      if (privilegedUnique.length) {
        reason += `, ${privilegedUnique.length} of which no one else on the team has`;
      }
      flags.push({
        severity: privilegedUnique.length ? 'high' : 'medium',
        type: 'privileged_access',
        identity: name,
        reason: reason + '.',
        items: (privilegedUnique.length ? privilegedUnique : access.privileged).slice(0, MAX_ITEMS_PER_FLAG),
      });
    }

    if (peerRules) {
      if (unique.length) {
        flags.push({
          severity: 'medium',
          type: 'unique_access',
          identity: name,
          reason: `Holds ${unique.length} item(s) no one else on the team has.`,
          items: unique.slice(0, MAX_ITEMS_PER_FLAG),
        });
      }

      if (teamMedian && total > teamMedian * OUTLIER_FACTOR && total - teamMedian >= OUTLIER_MIN_GAP) {
        flags.push({
          severity: 'medium',
          type: 'access_outlier',
          identity: name,
          reason: `Has ${total} access items vs a team median of ${formatNumber(teamMedian)}.`,
        });
      }

      const missing = sortedStrings([...baseline].filter((key) => !keys.has(key)).map(labelOf));
      if (baseline.size && missing.length * 2 > baseline.size) {
        flags.push({
          severity: 'low',
          type: 'missing_baseline',
          identity: name,
          reason:
            `Lacks ${missing.length} of the ${baseline.size} items nearly ` +
            'everyone else on the team has -- possibly not fully onboarded.',
          items: missing.slice(0, MAX_ITEMS_PER_FLAG),
        });
      }
    }

    if (teamUsesRoles && access.entitlements.length && !access.roles.length) {
      flags.push({
        severity: 'low',
        type: 'no_roles',
        identity: name,
        reason:
          `Has ${access.entitlements.length} entitlement(s) but no role, ` +
          'unlike most of the team -- access was granted piecemeal.',
      });
    }
  }

  // Array.prototype.sort is stable, like Python's sorted().
  return flags.sort(
    (a, b) =>
      SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] ||
      byCodePoint(String(a.identity), String(b.identity)),
  );
}

/** The Search API request body for one manager's direct reports, with access. */
export function directReportsSearch(managerId: string): Record<string, unknown> {
  return {
    indices: ['identities'],
    query: { query: `manager.id:"${managerId.replace(/"/g, '\\"')}"` },
    queryResultFilter: { includes: TEAM_FIELDS },
    sort: ['displayName', 'id'],
    includeNested: true,
  };
}
