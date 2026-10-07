/**
 * Business rules, ported from core/bulkaccess/rules.py so the page refuses
 * exactly what the Launcher form and the workflow refuse. rules.spec.ts mirrors
 * core/tests/test_core.py; keep the two in step.
 */
import type { ItemType, RuntimeConfig } from './runtime-config';

export const TYPE_LABELS: Record<ItemType, string> = {
  ACCESS_PROFILE: 'Access profile',
  ROLE: 'Role',
  ENTITLEMENT: 'Entitlement',
};

/** SailPoint limits on a generic approval task's text fields (rules.py). */
export const APPROVAL_NAME_MAX = 50;
export const APPROVAL_DESCRIPTION_MAX = 150;
export const APPROVAL_COMMENT_MAX = 150;

/** One access item as the workflow's Manage Access step needs it. */
export interface AccessItem {
  id: string;
  type: ItemType;
  name: string;
}

type RuleConfig = Pick<RuntimeConfig, 'incPattern' | 'incMessage' | 'peopleMax' | 'itemsMax' | 'catalogTypes'>;

export function incIsValid(cfg: Pick<RuntimeConfig, 'incPattern'>, value: string | null | undefined): boolean {
  return !!value && new RegExp(cfg.incPattern).test(value.trim());
}

export interface RequestDraft {
  requesterId: string;
  approverId: string | null | undefined;
  people: string[];
  items: { id: string; type: string }[];
  inc: string;
}

/** Everything wrong with a bulk request, as sentences (empty list = OK). Same order as rules.py. */
export function validateRequest(cfg: RuleConfig, draft: RequestDraft): string[] {
  const problems: string[] = [];
  const { requesterId, approverId, people, items, inc } = draft;
  if (!people.length) problems.push('Choose at least one person.');
  if (new Set(people).size > cfg.peopleMax) problems.push(`Choose at most ${cfg.peopleMax} people.`);
  if (!items.length) problems.push('Choose at least one access item.');
  if (items.length > cfg.itemsMax) problems.push(`Choose at most ${cfg.itemsMax} access items.`);
  if (items.some((i) => !cfg.catalogTypes.includes(i.type as ItemType))) {
    problems.push('One of the chosen items is not an allowed type.');
  }
  if (!approverId) {
    problems.push('Choose an approver.');
  } else if (approverId === requesterId) {
    // SailPoint reassigns self-approvals to another admin, so refuse up front.
    problems.push('The approver must be someone other than you.');
  }
  if (!incIsValid(cfg, inc)) problems.push(cfg.incMessage);
  return problems;
}

export function clip(text: string, limit: number): string {
  const flat = String(text).split(/\s+/).filter(Boolean).join(' ');
  return flat.length <= limit ? flat : flat.slice(0, limit - 1) + '…';
}

/**
 * The workflow writes "<INC>: <justification>" into the generic approval's
 * comment, which SailPoint caps at APPROVAL_COMMENT_MAX characters.
 */
export function justificationMax(inc: string, example = ''): number {
  return APPROVAL_COMMENT_MAX - 2 - Math.max(inc.trim().length, example.length);
}

/** A catalog entry as the Items step shows it. */
export interface CatalogOption {
  label: string;
  subLabel: string;
  description: string;
  source: string | null;
  value: AccessItem;
}

/** /v3/requestable-objects rows -> catalog options, filtered by type and name prefix (rules.catalog_options). */
export function catalogOptions(
  cfg: Pick<RuntimeConfig, 'catalogTypes' | 'nameStartsWith'>,
  requestable: Iterable<Record<string, unknown>>,
  sources: Record<string, string> = {},
): CatalogOption[] {
  const options: CatalogOption[] = [];
  for (const obj of requestable) {
    const kind = obj['type'] as ItemType;
    const id = String(obj['id']);
    const name = String(obj['name'] || id);
    if (!cfg.catalogTypes.includes(kind)) continue;
    if (cfg.nameStartsWith && !name.startsWith(cfg.nameStartsWith)) continue;
    const embedded = obj['source'] as { name?: string } | undefined;
    const source = sources[id] ?? (embedded && typeof embedded === 'object' ? embedded.name ?? null : null);
    options.push({
      label: name,
      subLabel: TYPE_LABELS[kind] + (source ? ` · ${source}` : ''),
      description: typeof obj['description'] === 'string' ? (obj['description'] as string) : '',
      source,
      value: { id, type: kind, name },
    });
  }
  return options.sort((a, b) => {
    const byName = a.label.toLowerCase().localeCompare(b.label.toLowerCase());
    return byName || a.value.type.localeCompare(b.value.type);
  });
}

/**
 * Find the INC number in free text (an access request comment such as
 * "INC0012345 | Bulk access request by …", or an approval name such as
 * "Bulk access INC0012345"). Each word is tested against the configured
 * pattern, so anchors like ^…$ keep working.
 */
export function extractInc(cfg: Pick<RuntimeConfig, 'incPattern'>, text: string | null | undefined): string | null {
  if (!text) return null;
  const re = new RegExp(cfg.incPattern);
  for (const word of text.split(/[\s|:,;()[\]{}]+/)) {
    if (word && re.test(word)) return word;
  }
  return null;
}

/** The generic approval name the workflow gives each bulk request (definitions.py: "Bulk access {inc}"). */
export const APPROVAL_NAME_PREFIX = 'Bulk access ';
