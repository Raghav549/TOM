# TOM Agent Execution V3

This batch defines the bounded execution controller used before TOM is allowed to claim a task is complete.

## Control loop

1. Parse the user's goal and constraints.
2. Retrieve relevant memory and available capabilities.
3. Build a bounded plan (maximum 40 steps per task).
4. Before every action, check required arguments, expected package and expected screen fingerprint.
5. Execute one action.
6. Observe the environment again.
7. Verify the intended state transition, not merely transport success.
8. On failure, retry only within a bounded attempt budget and re-ground first.
9. If the state is stale or contradictory, stop the current action and request a fresh observation.
10. Ask for confirmation before consequential operations.
11. Never claim success without a verified result.

## Research basis

The design follows the interleaved reasoning/acting principle from ReAct and the environment-state verification philosophy used by AndroidWorld. AndroidWorld specifically provides initialization, success checking and teardown logic for real Android tasks, which is the evaluation pattern TOM should emulate for its own device tests.

References:

- https://arxiv.org/abs/2210.03629
- https://arxiv.org/abs/2405.14573
- https://github.com/google-research/android_world

## Safety invariants

- Consequential actions remain fail-closed.
- A screen change invalidates action coordinates unless the action is re-grounded.
- Repeated identical failures cannot create an unbounded loop.
- A tool returning `success=true` is not itself proof of task completion.
- Credentials and secrets are never stored in task state or screenshots.
