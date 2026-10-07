import { Component, computed, inject, OnDestroy, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { MessageModule } from 'primeng/message';
import { TextareaModule } from 'primeng/textarea';

import { BulkApiService, type Person } from '../../bulk/bulk-api.service';
import { BulkConfigService } from '../../bulk/bulk-config.service';
import { describeError } from '../../bulk/errors';
import { RequestStore } from '../../bulk/request-store';
import { incIsValid } from '../../bulk/rules';

/** Step 3: one approver for the whole request, the ServiceNow INC number, and why. */
@Component({
  selector: 'app-approver-step',
  imports: [ButtonModule, FormsModule, InputTextModule, MessageModule, TextareaModule],
  templateUrl: './approver-step.component.html',
  styleUrl: './steps.scss',
})
export class ApproverStepComponent implements OnDestroy {
  protected readonly store = inject(RequestStore);
  protected readonly cfg = inject(BulkConfigService).config;
  private readonly api = inject(BulkApiService);

  protected readonly searching = signal(false);
  protected readonly error = signal('');
  private debounce: ReturnType<typeof setTimeout> | null = null;
  private seq = 0;

  /** Live INC check: shown as soon as something is typed. */
  protected readonly incError = computed(() => {
    const value = this.store.inc();
    return value.trim() && !incIsValid(this.cfg(), value) ? this.cfg().incMessage : '';
  });
  protected readonly incOk = computed(() => incIsValid(this.cfg(), this.store.inc()));
  protected readonly isSelf = computed(() => !!this.store.approver() && this.store.approver()!.id === this.store.requesterId());
  protected readonly isOnRequest = computed(() => {
    const a = this.store.approver();
    return !!a && this.store.people().some((p) => p.id === a.id);
  });

  protected onQuery(value: string): void {
    this.store.approverQuery.set(value);
    if (this.debounce) clearTimeout(this.debounce);
    this.debounce = setTimeout(() => void this.search(value), 300);
  }

  private async search(term: string): Promise<void> {
    const seq = ++this.seq;
    if (term.trim().length < 2) {
      this.store.approverResults.set([]);
      return;
    }
    this.searching.set(true);
    this.error.set('');
    try {
      const found = await this.api.searchPeople(term, 10);
      if (seq === this.seq) this.store.approverResults.set(found);
    } catch (err) {
      if (seq === this.seq) this.error.set(describeError(err));
    } finally {
      if (seq === this.seq) this.searching.set(false);
    }
  }

  protected isMe(p: Person): boolean {
    return p.id === this.store.requesterId();
  }

  protected choose(p: Person): void {
    this.store.approver.set(p);
    this.store.approverResults.set([]);
    this.store.approverQuery.set('');
  }

  ngOnDestroy(): void {
    if (this.debounce) clearTimeout(this.debounce);
  }
}
