import { computed, inject, Injectable, OnDestroy, signal } from '@angular/core';
import { SailpointPluginService } from '@core';

import { BulkApiService, type ExistingAccess, type Person, type Resolution } from './bulk-api.service';
import { BulkConfigService } from './bulk-config.service';
import { executionIdOf } from './my-requests';
import { describeError } from './errors';
import { clip, justificationMax, validateRequest, type CatalogOption } from './rules';

export type SubmissionState = 'starting' | 'waiting' | 'approved' | 'denied' | 'failed' | 'still-waiting' | 'error';

export interface SubmissionStatus {
  state: SubmissionState;
  executionId: string | null;
  approvalId: string | null;
  approver: string;
  inc: string;
  message: string;
  startedAt: number;
}

/** Poll quickly while the approval is being created, then back off. */
const POLL_SCHEDULE_MS = [2000, 2000, 3000, 3000, 5000, 5000, 10000];
const POLL_FOR_MS = 10 * 60 * 1000;

/** The request being built on the New request tab, and its submission. */
@Injectable({ providedIn: 'root' })
export class RequestStore implements OnDestroy {
  private readonly api = inject(BulkApiService);
  private readonly plugin = inject(SailpointPluginService);
  private readonly bulkConfig = inject(BulkConfigService);

  readonly step = signal(1);
  readonly people = signal<Person[]>([]);
  readonly items = signal<CatalogOption[]>([]);
  readonly approver = signal<Person | null>(null);
  readonly inc = signal('');
  readonly justification = signal('');
  readonly existing = signal<ExistingAccess[]>([]);
  readonly submission = signal<SubmissionStatus | null>(null);

  // Step UI state lives here too, so switching tabs keeps it (and demo scenarios can set it).
  readonly peopleQuery = signal('');
  readonly peopleResults = signal<Person[]>([]);
  readonly pasteText = signal('');
  readonly resolution = signal<Resolution | null>(null);
  readonly approverQuery = signal('');
  readonly approverResults = signal<Person[]>([]);
  readonly itemFilter = signal('');

  readonly justificationMax = computed(() => justificationMax(this.inc(), this.bulkConfig.config().incExample));
  readonly requesterId = computed(() => this.plugin.user()?.id ?? '');
  readonly problems = computed(() => {
    const problems = validateRequest(this.bulkConfig.config(), {
      requesterId: this.requesterId(),
      approverId: this.approver()?.id,
      people: this.people().map((p) => p.id),
      items: this.items().map((o) => o.value),
      inc: this.inc(),
    });
    const max = this.justificationMax();
    if (!this.justification().trim()) problems.push('Enter a business justification.');
    else if (this.justification().trim().length > max) problems.push(`Keep the justification to ${max} characters.`);
    return problems;
  });

  private timer: ReturnType<typeof setTimeout> | null = null;

  addPeople(found: Person[]): number {
    const max = this.bulkConfig.config().peopleMax;
    const current = this.people();
    const ids = new Set(current.map((p) => p.id));
    const fresh = found
      .filter((p) => !ids.has(p.id) && ids.add(p.id))
      .slice(0, Math.max(0, max - current.length));
    if (fresh.length) this.people.set([...current, ...fresh]);
    return fresh.length;
  }

  removePerson(id: string): void {
    this.people.update((list) => list.filter((p) => p.id !== id));
  }

  /** Check which chosen people already have the chosen items (shown as warnings on the review step). */
  async checkExisting(): Promise<void> {
    this.existing.set([]);
    this.existing.set(await this.api.existingAccess(this.people().map((p) => p.id), this.items().map((o) => o.value)));
  }

  async submit(): Promise<void> {
    const cfg = this.bulkConfig.config();
    if (this.problems().length || this.submission()?.state === 'starting') return;
    const approver = this.approver()!;
    const inc = this.inc().trim();
    this.submission.set({ state: 'starting', executionId: null, approvalId: null, approver: approver.name, inc,
      message: 'Starting the workflow…', startedAt: Date.now() });
    try {
      const workflowId = await this.api.workflowId(cfg);
      const executionId = await this.api.submit(workflowId, {
        people: this.people().map((p) => p.id),
        items: this.items().map((o) => o.value),
        approverId: approver.id,
        requesterId: this.requesterId(),
        inc,
        justification: clip(this.justification(), this.justificationMax()),
      });
      this.patch({ state: 'waiting', executionId, message: `Sent. Waiting for ${approver.name} to decide.` });
      this.schedule(0);
    } catch (err) {
      this.patch({ state: 'error', message: describeError(err) });
    }
  }

  /** Start over with an empty form (keeps nothing from the last request). */
  reset(): void {
    this.stop();
    this.step.set(1);
    this.people.set([]);
    this.items.set([]);
    this.approver.set(null);
    this.inc.set('');
    this.justification.set('');
    this.existing.set([]);
    this.submission.set(null);
    this.peopleQuery.set('');
    this.peopleResults.set([]);
    this.pasteText.set('');
    this.resolution.set(null);
    this.approverQuery.set('');
    this.approverResults.set([]);
    this.itemFilter.set('');
  }

  ngOnDestroy(): void {
    this.stop();
  }

  private stop(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  private patch(change: Partial<SubmissionStatus>): void {
    this.submission.update((s) => (s ? { ...s, ...change } : s));
  }

  private schedule(attempt: number): void {
    this.stop();
    const delay = POLL_SCHEDULE_MS[Math.min(attempt, POLL_SCHEDULE_MS.length - 1)];
    this.timer = setTimeout(() => void this.poll(attempt), delay);
  }

  /** One round: the execution's status, plus the approval it created (found by execution ID). */
  private async poll(attempt: number): Promise<void> {
    const s = this.submission();
    if (!s?.executionId) return;
    try {
      const [execution, approvals] = await Promise.all([this.api.execution(s.executionId), this.api.approvals()]);
      const approval = approvals.find((a) => executionIdOf(a) === s.executionId);
      const approver = approval?.approvers?.[0]?.name ?? s.approver;
      if (approval) this.patch({ approvalId: approval.id, approver });

      if (approval?.status === 'APPROVED' || approval?.status === 'REJECTED' || approval?.status === 'EXPIRED'
          || approval?.status === 'CANCELLED') {
        // The list leaves out who decided; the detail call has it.
        Object.assign(approval, await this.api.approval(approval.id).catch(() => ({})));
        const denied = approval.status !== 'APPROVED';
        const mode = this.bulkConfig.config().mode;
        const what = denied
          ? `${approval.status === 'REJECTED' ? `Denied by ${approval.rejectedBy?.[0]?.name ?? approver}` : `Approval ${approval.status.toLowerCase()}`}. Nothing was requested.`
          : `Approved by ${approval.approvedBy?.[0]?.name ?? approver}. ` + (mode === 'live'
            ? 'Access is being requested for every person; follow it on My bulk requests.'
            : 'Dry-run mode: nothing was requested.');
        this.patch({ state: denied ? 'denied' : 'approved', message: what });
        // Keep polling until the workflow itself finishes (its emails go out last).
        if (execution.status !== 'Running') return;
      } else if (execution.status === 'Failed' || execution.status === 'Canceled') {
        this.patch({ state: 'failed', message: `The workflow ${execution.status.toLowerCase()} before an approval was decided. `
          + 'An administrator can see why in Admin > Workflows > executions.' });
        return;
      } else if (execution.status === 'Completed' && !approval) {
        this.patch({ state: 'failed', message: 'The workflow finished without creating an approval '
          + '(the INC number or approver was rejected). Check your email for details.' });
        return;
      } else {
        this.patch({ state: 'waiting', message: approval ? `Waiting for ${approver} to approve or deny.` : 'Creating the approval…' });
      }
    } catch (err) {
      // A failed poll is not fatal; try again on the next round.
      this.patch({ message: `Still checking… (${describeError(err)})` });
    }
    if (Date.now() - s.startedAt > POLL_FOR_MS) {
      this.patch({ state: s.state === 'waiting' ? 'still-waiting' : s.state,
        message: `Still waiting for ${this.submission()?.approver}. Follow it on the My bulk requests tab.` });
      return;
    }
    this.schedule(attempt + 1);
  }
}
