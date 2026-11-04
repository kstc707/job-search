/**
 * `notify:<template>`: queue a message in the transactional outbox. It is written in the same store
 * commit as the transition, and sent after the commit; a notification outage never blocks the workflow.
 */
export default function notify(ctx, template) {
  ctx.enqueueNotification(ctx.permit, template);
}
