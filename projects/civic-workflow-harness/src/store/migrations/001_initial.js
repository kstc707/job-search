export const version = 1;
export const description = 'Initial store: permits, processed webhook events, reconciliation queue, notification outbox';

export function up(state) {
  return {
    ...state,
    permits: {},
    processedEvents: {},
    orphanEvents: [],
    reconciliation: [],
    outbox: [],
    counters: { permit: 0, message: 0, inspection: 0, reconciliation: 0 },
    migrationLog: state.migrationLog ?? [],
  };
}

export function down() {
  throw new Error('Refusing to drop the initial schema');
}
