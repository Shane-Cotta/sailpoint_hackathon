import { Component, computed, inject, OnInit, output, signal } from '@angular/core';
import { SailpointPluginService } from '@core';
import { ButtonModule } from 'primeng/button';
import { MessageModule } from 'primeng/message';
import { ProgressSpinnerModule } from 'primeng/progressspinner';
import { TagModule } from 'primeng/tag';

import { BulkConfigService } from '../../bulk/bulk-config.service';
import { RequestStore } from '../../bulk/request-store';
import { TYPE_LABELS } from '../../bulk/rules';
import type { ItemType } from '../../bulk/runtime-config';

/** Step 4: check everything, submit, then follow the approval. */
@Component({
  selector: 'app-review-step',
  imports: [ButtonModule, MessageModule, ProgressSpinnerModule, TagModule],
  templateUrl: './review-step.component.html',
  styleUrl: './steps.scss',
})
export class ReviewStepComponent implements OnInit {
  protected readonly store = inject(RequestStore);
  protected readonly cfg = inject(BulkConfigService).config;
  protected readonly configError = inject(BulkConfigService).error;
  private readonly plugin = inject(SailpointPluginService);

  /** Ask the host page to show the My bulk requests tab. */
  readonly showHistory = output<void>();

  protected readonly checking = signal(false);
  protected readonly isAdmin = computed(() => this.plugin.user()?.capabilities?.isOrgAdmin ?? false);
  protected readonly canSubmit = computed(() => !this.store.problems().length && this.isAdmin() && !this.configError()
    && (!this.store.submission() || this.store.submission()!.state === 'error'));

  /** "Alan Bradley already has UCSF Bulk Test Access", grouped per item. */
  protected readonly warnings = computed(() => {
    const names = new Map(this.store.people().map((p) => [p.id, p.name]));
    const byItem = new Map<string, { item: string; assigned: string[]; pending: string[] }>();
    for (const e of this.store.existing()) {
      const item = this.store.items().find((o) => o.value.id === e.itemId)?.label ?? e.itemId;
      const row = byItem.get(item) ?? { item, assigned: [], pending: [] };
      (e.status === 'ASSIGNED' ? row.assigned : row.pending).push(names.get(e.personId) ?? e.personId);
      byItem.set(item, row);
    }
    return [...byItem.values()];
  });

  ngOnInit(): void {
    if (!this.store.submission()) void this.check();
  }

  private async check(): Promise<void> {
    this.checking.set(true);
    try {
      await this.store.checkExisting();
    } finally {
      this.checking.set(false);
    }
  }

  protected typeLabel(t: ItemType): string {
    return TYPE_LABELS[t] ?? t;
  }

  protected requestCount(): number {
    return this.store.people().length;
  }
}
