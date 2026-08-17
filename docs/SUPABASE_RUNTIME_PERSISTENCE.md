# TOM durable runtime persistence

TOM uses the Supabase project configured through `TOM_SUPABASE_URL` and `TOM_SUPABASE_SERVICE_ROLE_KEY` as the durable server-side state store for long-running agent tasks.

## Tables

- `tom_agent_tasks`: authoritative task lifecycle, current step, context and current predicate.
- `tom_agent_actions`: one row per action attempt, including grounding, predicate and verification evidence.
- `tom_agent_events`: ordered task event journal used for reconnect replay/audit.

## Recovery contract

A Core restart must recover by reading the task snapshot before issuing any new consequential action. The recovered action must be checked for terminal status and predicate evidence; a transport ACK alone is never sufficient. For non-terminal tasks, TOM re-observes the device/browser first and then re-plans from the recovered goal, memory, current predicate and last verified state.

## Secrets

The service-role key is server-only and must never be sent to Android or the browser. Supabase RLS is enabled on all three tables; policies grant access only to the server `service_role`.
