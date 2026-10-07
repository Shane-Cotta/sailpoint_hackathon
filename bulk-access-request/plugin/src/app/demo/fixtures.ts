/**
 * Made-up data for ?demo=… mode and for unit tests. Nothing here comes from a
 * real tenant: names, IDs and INC numbers are fictitious.
 */
import type { AccessRequestStatus, GenericApproval } from '../bulk/bulk-api.service';
import { parseRuntimeConfig, type RuntimeConfig } from '../bulk/runtime-config';

export const DEMO_ME = { id: 'd0000000000000000000000000000001', name: 'Jordan Lee', email: 'jordan.lee@example.edu' };

export const DEMO_CONFIG: RuntimeConfig = parseRuntimeConfig({
  prefix: 'UCSF',
  mode: 'live',
  workflowName: 'UCSF Bulk Access Request (Plugin)',
  workflowId: 'demo-workflow',
  incPattern: '^INC\\d{7}$',
  incMessage: 'Enter a ServiceNow incident number: INC followed by 7 digits, e.g. INC0012345.',
  incExample: 'INC0012345',
  peopleMax: 50,
  itemsMax: 25,
  catalogTypes: ['ACCESS_PROFILE', 'ROLE', 'ENTITLEMENT'],
  nameStartsWith: null,
  launcherName: 'UCSF Bulk Access Request',
});

const people: [string, string, string][] = [
  ['Alan Bradley', 'alan.bradley', 'Radiology'],
  ['Andrei Popescu', 'andrei.popescu', 'Radiology'],
  ['Aisha Bello', 'aisha.bello', 'Clinical Informatics'],
  ['Amelia Thornton', 'amelia.thornton', 'Radiology'],
  ['Anouk De Vries', 'anouk.devries', 'Pediatrics'],
  ['Beatriz Santos', 'beatriz.santos', 'Radiology'],
  ['Brenda Cooper', 'brenda.cooper', 'Nursing'],
  ['Bruno Marchetti', 'bruno.marchetti', 'Radiology'],
  ['Carmen Ruiz', 'carmen.ruiz', 'Oncology'],
  ['Claire Beaumont', 'claire.beaumont', 'Radiology'],
  ['Diego Alvarez', 'diego.alvarez', 'Emergency Medicine'],
  ['Andrea Kim', 'andrea.kim', 'Radiology'],
  ['Andrea Kim', 'andrea.kim2', 'Pharmacy'],
];

/** Search documents (POST /v3/search, identities). */
export const DEMO_IDENTITIES = [
  { id: DEMO_ME.id, name: 'jordan.lee', displayName: DEMO_ME.name, email: DEMO_ME.email, attributes: { department: 'IT Identity Services' } },
  ...people.map(([name, user, dept], i) => ({
    id: `d${String(i + 10).padStart(31, '0')}`,
    name: user,
    displayName: name,
    email: `${user}@example.edu`,
    attributes: { department: dept },
  })),
];

export function demoPerson(displayName: string, nth = 0) {
  const doc = DEMO_IDENTITIES.filter((d) => d.displayName === displayName)[nth];
  if (!doc) throw new Error(`no demo person ${displayName}`);
  return { id: doc.id, name: doc.displayName, email: doc.email, detail: doc.attributes.department };
}

/** GET /v3/requestable-objects rows, plus the source each one comes from (search). */
export const DEMO_CATALOG: { row: Record<string, unknown>; source: string | null }[] = [
  ['UCSF Bulk Test Access', 'ACCESS_PROFILE', 'UCSF SaaS', 'Read-only group on the UCSF SaaS demo source.'],
  ['PACS Radiologist Workstation', 'ACCESS_PROFILE', 'PACS', 'View and report on imaging studies.'],
  ['Epic - Clinician Read Only', 'ACCESS_PROFILE', 'Epic', 'Chart review without order entry.'],
  ['Radiology Department Staff', 'ROLE', null, 'Baseline access for everyone in Radiology.'],
  ['VPN - Remote Access', 'ACCESS_PROFILE', 'Active Directory', 'GlobalProtect VPN for off-site work.'],
  ['Box - Imaging Research Share', 'ENTITLEMENT', 'Box', 'Read/write on the imaging research folder.'],
  ['ServiceNow - ITIL User', 'ROLE', null, 'Work incidents and requests in ServiceNow.'],
  ['Zoom - Licensed User', 'ENTITLEMENT', 'Zoom', 'Meetings longer than 40 minutes.'],
  ['Teams - Radiology Channel', 'ENTITLEMENT', 'Entra ID', 'Membership of the Radiology Teams channel.'],
].map(([name, type, source, description], i) => ({
  row: { id: `c${String(i + 1).padStart(31, '0')}`, name, type, description, requestStatus: null },
  source,
}));

export function demoItem(name: string) {
  const hit = DEMO_CATALOG.find((c) => c.row['name'] === name)!;
  const type = hit.row['type'] as 'ACCESS_PROFILE' | 'ROLE' | 'ENTITLEMENT';
  const label = { ACCESS_PROFILE: 'Access profile', ROLE: 'Role', ENTITLEMENT: 'Entitlement' }[type];
  return {
    label: name,
    subLabel: label + (hit.source ? ` · ${hit.source}` : ''),
    description: String(hit.row['description']),
    source: hit.source,
    value: { id: String(hit.row['id']), type, name },
  };
}

/** Who already holds what (requestable-objects?identity-id=…). */
export const DEMO_HELD: Record<string, Record<string, 'ASSIGNED' | 'PENDING'>> = {
  [demoPerson('Alan Bradley').id]: { [demoItem('UCSF Bulk Test Access').value.id]: 'ASSIGNED' },
  [demoPerson('Beatriz Santos').id]: { [demoItem('PACS Radiologist Workstation').value.id]: 'PENDING' },
};

export const DEMO_NEW_EXECUTION = 'e0000000-0000-4000-8000-000000000099';

function approval(id: string, inc: string, status: string, approver: string, created: string,
                  completed: string | null, executionId: string): GenericApproval {
  return {
    id,
    name: [{ value: `Bulk access ${inc}`, locale: 'en_US' }],
    description: [{ value: `UCSF bulk access request ${inc} from ${DEMO_ME.name}` }],
    status,
    createdDate: created,
    completedDate: completed,
    requester: { identityID: DEMO_ME.id, name: DEMO_ME.name },
    approvers: [{ identityID: demoPerson(approver).id, name: approver }],
    approvedBy: status === 'APPROVED' ? [{ name: approver }] : null,
    rejectedBy: status === 'REJECTED' ? [{ name: approver }] : null,
    referenceData: [{ id: executionId, type: 'workflowExecutionId' }],
  };
}

/** Approvals already in the tenant (the "My bulk requests" history). */
export const DEMO_APPROVALS: GenericApproval[] = [
  approval('a0000000-0000-4000-8000-000000000001', 'INC0048213', 'PENDING', 'Aisha Bello',
    '2026-10-07T15:12:00Z', null, 'e0000000-0000-4000-8000-000000000001'),
  approval('a0000000-0000-4000-8000-000000000002', 'INC0047950', 'APPROVED', 'Carmen Ruiz',
    '2026-10-06T09:30:00Z', '2026-10-06T10:02:00Z', 'e0000000-0000-4000-8000-000000000002'),
  approval('a0000000-0000-4000-8000-000000000003', 'INC0047711', 'REJECTED', 'Aisha Bello',
    '2026-10-03T16:45:00Z', '2026-10-04T08:15:00Z', 'e0000000-0000-4000-8000-000000000003'),
  approval('a0000000-0000-4000-8000-000000000004', 'INC0047711', 'CANCELLED', 'Diego Alvarez',
    '2026-10-03T16:20:00Z', '2026-10-03T16:40:00Z', 'e0000000-0000-4000-8000-000000000004'),
];

/** The approval the "submitted" scenario's workflow creates. */
export function demoNewApproval(inc: string, approver: string): GenericApproval {
  return approval('a0000000-0000-4000-8000-000000000099', inc, 'PENDING', approver,
    new Date().toISOString(), null, DEMO_NEW_EXECUTION);
}

function request(person: string, item: string, state: string, created: string, inc: string, approver: string): AccessRequestStatus {
  const p = demoPerson(person);
  const it = demoItem(item);
  return {
    id: it.value.id, name: item, type: it.value.type, state, created,
    requestedFor: { id: p.id, name: p.name },
    requester: { id: DEMO_ME.id, name: DEMO_ME.name },
    requesterComment: { comment: `${inc} | Bulk access request by ${DEMO_ME.name} | Approved by ${approver} | New PACS rollout` },
  };
}

export const DEMO_REQUESTS: AccessRequestStatus[] = [
  ...['Amelia Thornton', 'Bruno Marchetti', 'Claire Beaumont'].flatMap((p, i) => [
    request(p, 'PACS Radiologist Workstation', i === 2 ? 'EXECUTING' : 'REQUEST_COMPLETED', '2026-10-06T10:03:00Z', 'INC0047950', 'Carmen Ruiz'),
    request(p, 'Radiology Department Staff', 'REQUEST_COMPLETED', '2026-10-06T10:03:00Z', 'INC0047950', 'Carmen Ruiz'),
  ]),
  // An ordinary access request without an INC: the page ignores it.
  { id: 'x', name: 'Zoom - Licensed User', type: 'ENTITLEMENT', state: 'REQUEST_COMPLETED', created: '2026-10-01T10:00:00Z',
    requestedFor: { id: DEMO_ME.id, name: DEMO_ME.name }, requester: { id: DEMO_ME.id }, requesterComment: { comment: 'need it' } },
];
