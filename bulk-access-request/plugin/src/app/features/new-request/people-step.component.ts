import { Component, inject, OnDestroy, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { ChipModule } from 'primeng/chip';
import { InputTextModule } from 'primeng/inputtext';
import { MessageModule } from 'primeng/message';
import { TextareaModule } from 'primeng/textarea';

import { BulkApiService, splitPasted, type Person } from '../../bulk/bulk-api.service';
import { BulkConfigService } from '../../bulk/bulk-config.service';
import { describeError } from '../../bulk/errors';
import { RequestStore } from '../../bulk/request-store';

/** Step 1: who needs the access. Type-ahead search, or paste a list of IDs, usernames or emails. */
@Component({
  selector: 'app-people-step',
  imports: [ButtonModule, ChipModule, FormsModule, InputTextModule, MessageModule, TextareaModule],
  templateUrl: './people-step.component.html',
  styleUrl: './steps.scss',
})
export class PeopleStepComponent implements OnDestroy {
  protected readonly store = inject(RequestStore);
  protected readonly cfg = inject(BulkConfigService).config;
  private readonly api = inject(BulkApiService);

  protected readonly searching = signal(false);
  protected readonly resolving = signal(false);
  protected readonly error = signal('');
  private debounce: ReturnType<typeof setTimeout> | null = null;
  private searchSeq = 0;

  protected onQuery(value: string): void {
    this.store.peopleQuery.set(value);
    if (this.debounce) clearTimeout(this.debounce);
    this.debounce = setTimeout(() => void this.search(value), 300);
  }

  private async search(term: string): Promise<void> {
    const seq = ++this.searchSeq;
    if (term.trim().length < 2) {
      this.store.peopleResults.set([]);
      return;
    }
    this.searching.set(true);
    this.error.set('');
    try {
      const found = await this.api.searchPeople(term);
      if (seq === this.searchSeq) this.store.peopleResults.set(found);
    } catch (err) {
      if (seq === this.searchSeq) this.error.set(describeError(err));
    } finally {
      if (seq === this.searchSeq) this.searching.set(false);
    }
  }

  protected isChosen(p: Person): boolean {
    return this.store.people().some((x) => x.id === p.id);
  }

  protected get full(): boolean {
    return this.store.people().length >= this.cfg().peopleMax;
  }

  protected add(p: Person): void {
    this.store.addPeople([p]);
  }

  protected async resolvePaste(): Promise<void> {
    const tokens = splitPasted(this.store.pasteText());
    if (!tokens.length) return;
    this.resolving.set(true);
    this.error.set('');
    try {
      const result = await this.api.resolvePeople(tokens);
      this.store.addPeople(result.resolved);
      this.store.resolution.set(result);
      // Leave only what still needs attention in the box.
      this.store.pasteText.set([...result.unresolved, ...result.ambiguous.map((a) => a.token)].join('\n'));
    } catch (err) {
      this.error.set(describeError(err));
    } finally {
      this.resolving.set(false);
    }
  }

  /** Pick one of several identities a pasted token matched. */
  protected pickAmbiguous(token: string, p: Person): void {
    this.store.addPeople([p]);
    this.store.resolution.update((r) => r && { ...r, ambiguous: r.ambiguous.filter((a) => a.token !== token) });
    this.store.pasteText.update((text) => splitPasted(text).filter((t) => t !== token).join('\n'));
  }

  ngOnDestroy(): void {
    if (this.debounce) clearTimeout(this.debounce);
  }
}
