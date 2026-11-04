// Transactional outbox for notifications. Messages are queued inside the same store commit as the
// workflow change, then sent outside the write lock. A failure keeps the message pending (retried on
// the next dispatch); after maxAttempts it is dead-lettered and shows up in /health and /admin/outbox.
export function createOutbox({ store, notify, maxAttempts = 5, log = () => {} }) {
  let running = null;
  let again = false;

  async function runOnce() {
    const ids = store.read().outbox.filter((e) => e.status === 'pending').map((e) => e.id);
    for (const id of ids) {
      const entry = store.read().outbox.find((e) => e.id === id);
      if (!entry || entry.status !== 'pending') continue;
      let error = null;
      try {
        await notify.send({ to: entry.to, channel: entry.channel, template: entry.template, data: entry.data, messageId: entry.id });
      } catch (e) {
        error = e;
      }
      await store.mutate((s) => {
        const e = s.outbox.find((x) => x.id === id);
        if (!e) return;
        e.attempts += 1;
        e.lastAttemptAt = new Date().toISOString();
        if (!error) {
          e.status = 'sent';
          e.sentAt = e.lastAttemptAt;
          e.lastError = null;
        } else {
          e.lastError = `${error.code ?? 'error'}: ${error.message}`;
          if (e.attempts >= maxAttempts) e.status = 'dead';
        }
      });
      if (error) log({ msg: 'notification failed', id, error: error.message });
    }
  }

  function dispatch() {
    if (running) {
      again = true;
      return running;
    }
    running = (async () => {
      try {
        do {
          again = false;
          await runOnce();
        } while (again);
      } finally {
        running = null;
      }
    })();
    return running;
  }

  function stats(state = store.read()) {
    const count = (st) => state.outbox.filter((e) => e.status === st).length;
    return { pending: count('pending'), sent: count('sent'), dead: count('dead'), total: state.outbox.length };
  }

  return { dispatch, stats, idle: () => running ?? Promise.resolve() };
}
