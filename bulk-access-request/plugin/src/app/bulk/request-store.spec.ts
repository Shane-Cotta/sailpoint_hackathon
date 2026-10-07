import { TestBed } from '@angular/core/testing';
import { SailpointPluginService } from '@core';

import { applyScenario } from '../demo/demo';
import { DEMO_ME, DEMO_NEW_EXECUTION, demoPerson } from '../demo/fixtures';
import { providePluginTesting } from '../testing/plugin.testing';
import { BulkConfigService } from './bulk-config.service';
import { describeError } from './errors';
import { NavService } from './nav';
import { RequestStore } from './request-store';

describe('RequestStore', () => {
  let store: RequestStore;

  beforeEach(async () => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({ providers: providePluginTesting() });
    await TestBed.inject(BulkConfigService).load();
    store = TestBed.inject(RequestStore);
  });

  afterEach(() => {
    store.reset();
    vi.useRealTimers();
  });

  it('blocks submitting until the request is complete, with the same messages as the core', () => {
    expect(store.problems()).toEqual(expect.arrayContaining([
      'Choose at least one person.', 'Choose at least one access item.', 'Choose an approver.',
      'Enter a business justification.',
    ]));
    store.approver.set(demoPerson('Aisha Bello'));
    store.approver.set({ id: DEMO_ME.id, name: DEMO_ME.name });
    expect(store.problems()).toContain('The approver must be someone other than you.');
  });

  it('caps the people list at the configured maximum and skips duplicates', () => {
    const p = demoPerson('Alan Bradley');
    expect(store.addPeople([p, p])).toBe(1);
    expect(store.addPeople([p])).toBe(0);
    TestBed.inject(BulkConfigService).config.update((c) => ({ ...c, peopleMax: 2 }));
    expect(store.addPeople([demoPerson('Aisha Bello'), demoPerson('Carmen Ruiz')])).toBe(1);
    expect(store.people()).toHaveLength(2);
  });

  it('submits, then reports "Waiting for <approver>" once the approval exists', async () => {
    applyScenario('review', store, TestBed.inject(NavService));
    const plugin = TestBed.inject(SailpointPluginService);
    const post = vi.spyOn(plugin, 'post');
    expect(store.problems()).toEqual([]);

    const done = store.submit();
    await vi.advanceTimersByTimeAsync(1000);
    await done;
    expect(post).toHaveBeenCalledWith('/v3/workflows/demo-workflow/test', {
      input: expect.objectContaining({
        people: store.people().map((x) => x.id),
        items: store.items().map((o) => o.value),
        approverId: demoPerson('Aisha Bello').id,
        requesterId: DEMO_ME.id,
        inc: 'INC0048391',
      }),
    });
    expect(store.submission()).toMatchObject({ state: 'waiting', executionId: DEMO_NEW_EXECUTION });

    await vi.advanceTimersByTimeAsync(5000);
    expect(store.submission()).toMatchObject({ state: 'waiting', message: 'Waiting for Aisha Bello to approve or deny.' });
    expect(store.submission()?.approvalId).toBeTruthy();
  });

  it('explains permission errors in terms of ORG_ADMIN and the Launcher', () => {
    expect(describeError({ status: 403 })).toContain('ORG_ADMIN');
    expect(describeError({ status: 400, body: { messages: [{ text: 'bad input' }] } })).toBe('bad input');
  });
});
