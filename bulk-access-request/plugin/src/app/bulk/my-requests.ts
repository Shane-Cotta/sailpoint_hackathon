/**
 * "My bulk requests": the signed-in user's bulk requests, grouped by INC.
 *
 * SailPoint has no single "bulk request" object, so the page joins two lists:
 *  - generic approvals the plugin workflow created ("Bulk access <INC>"), one per
 *    submission, which carry the approver and the decision;
 *  - access requests the workflow made after approval (live mode), whose
 *    comment starts with the INC.
 */
import type { AccessRequestStatus, GenericApproval } from './bulk-api.service';
import type { RuntimeConfig } from './runtime-config';
import { APPROVAL_NAME_PREFIX, extractInc } from './rules';

export type GroupStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED' | 'EXPIRED' | 'REQUESTED';

export interface Submission {
  approvalId: string;
  executionId: string | null;
  status: string;
  approver: string;
  decidedBy: string | null;
  created: string;
  completed: string | null;
  description: string;
}

export interface RequestRow {
  person: string;
  item: string;
  type: string;
  state: string;
  created: string;
}

export interface BulkGroup {
  inc: string;
  status: GroupStatus;
  /** Most recent submission first. */
  submissions: Submission[];
  requests: RequestRow[];
  people: number;
  items: number;
  lastActivity: string;
}

export function approvalName(a: GenericApproval): string {
  return a.name?.[0]?.value ?? '';
}

export function executionIdOf(a: GenericApproval): string | null {
  return a.referenceData?.find((r) => r.type === 'workflowExecutionId')?.id ?? null;
}

/** Is this approval one of ours (created by the plugin or Launcher workflow)? */
export function isBulkApproval(a: GenericApproval): boolean {
  return approvalName(a).startsWith(APPROVAL_NAME_PREFIX);
}

function toSubmission(a: GenericApproval): Submission {
  const decided = a.approvedBy?.[0]?.name ?? a.rejectedBy?.[0]?.name ?? null;
  return {
    approvalId: a.id,
    executionId: executionIdOf(a),
    status: a.status,
    approver: (a.approvers ?? []).map((x) => x.name).filter(Boolean).join(', ') || 'unknown',
    decidedBy: decided,
    created: a.createdDate ?? '',
    completed: a.completedDate ?? null,
    description: a.description?.[0]?.value ?? '',
  };
}

const KNOWN: GroupStatus[] = ['PENDING', 'APPROVED', 'REJECTED', 'CANCELLED', 'EXPIRED'];

export function groupByInc(
  cfg: Pick<RuntimeConfig, 'incPattern'>,
  requesterId: string,
  approvals: GenericApproval[],
  requests: AccessRequestStatus[],
): BulkGroup[] {
  const groups = new Map<string, BulkGroup>();
  const group = (inc: string) => {
    let g = groups.get(inc);
    if (!g) {
      g = { inc, status: 'REQUESTED', submissions: [], requests: [], people: 0, items: 0, lastActivity: '' };
      groups.set(inc, g);
    }
    return g;
  };

  for (const a of approvals) {
    if (!isBulkApproval(a) || a.requester?.identityID !== requesterId) continue;
    const inc = extractInc(cfg, approvalName(a));
    if (inc) group(inc).submissions.push(toSubmission(a));
  }
  for (const r of requests) {
    if (r.requester && r.requester.id !== requesterId) continue;
    const inc = extractInc(cfg, r.requesterComment?.comment);
    if (!inc) continue;
    group(inc).requests.push({
      person: r.requestedFor?.name ?? r.requestedFor?.id ?? '?',
      item: r.name,
      type: r.type,
      state: r.state,
      created: r.created ?? '',
    });
  }

  for (const g of groups.values()) {
    g.submissions.sort((x, y) => y.created.localeCompare(x.created));
    g.requests.sort((x, y) => x.person.localeCompare(y.person) || x.item.localeCompare(y.item));
    const latest = g.submissions[0]?.status as GroupStatus | undefined;
    g.status = latest && KNOWN.includes(latest) ? latest : 'REQUESTED';
    g.people = new Set(g.requests.map((r) => r.person)).size;
    g.items = new Set(g.requests.map((r) => r.item)).size;
    g.lastActivity = [...g.submissions.map((s) => s.completed || s.created), ...g.requests.map((r) => r.created)]
      .filter(Boolean)
      .sort()
      .at(-1) ?? '';
  }
  return [...groups.values()].sort((a, b) => b.lastActivity.localeCompare(a.lastActivity));
}

/** Plain-English label and p-tag severity for a group or submission status. */
export function statusLabel(status: string): { label: string; severity: 'success' | 'warn' | 'danger' | 'info' | 'secondary' } {
  switch (status) {
    case 'PENDING': return { label: 'Waiting for approval', severity: 'warn' };
    case 'APPROVED': return { label: 'Approved', severity: 'success' };
    case 'REJECTED': return { label: 'Denied', severity: 'danger' };
    case 'CANCELLED': return { label: 'Cancelled', severity: 'secondary' };
    case 'EXPIRED': return { label: 'Expired', severity: 'secondary' };
    case 'REQUESTED': return { label: 'Requested', severity: 'info' };
    default: return { label: status, severity: 'secondary' };
  }
}

/** Access request states (/v3/access-request-status) in plain English. */
export function requestStateLabel(state: string): { label: string; severity: 'success' | 'warn' | 'danger' | 'info' | 'secondary' } {
  switch (state) {
    case 'REQUEST_COMPLETED': return { label: 'Done', severity: 'success' };
    case 'EXECUTING': return { label: 'Provisioning', severity: 'info' };
    case 'PENDING': return { label: 'Pending', severity: 'warn' };
    case 'REJECTED': return { label: 'Rejected', severity: 'danger' };
    case 'ERROR': return { label: 'Error', severity: 'danger' };
    case 'CANCELLED': return { label: 'Cancelled', severity: 'secondary' };
    case 'NOT_ALL_ITEMS_PROVISIONED': return { label: 'Partly provisioned', severity: 'warn' };
    default: return { label: state, severity: 'secondary' };
  }
}
