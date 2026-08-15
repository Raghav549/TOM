# TOM research base

This is the research-to-engineering map used for TOM v2. It intentionally records methods rather than copying any paper's private reasoning or implementation.

## ReAct — observe/act interleaving

Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models* (2022).

TOM mapping:
- planner chooses the next action from current state/history,
- external observations are fed back after actions,
- bounded recovery handles exceptions instead of committing to a fixed open-loop plan.

Reference: https://arxiv.org/abs/2210.03629

## WebArena — realistic long-horizon web work

Zhou et al., *WebArena: A Realistic Web Environment for Building Autonomous Agents* (2023).

TOM mapping:
- evaluate multi-step workflows rather than single clicks,
- keep web tasks grounded in real application state,
- measure end-to-end completion rather than textual plan quality.

Reference: https://arxiv.org/abs/2307.13854

## OSWorld — execution-based computer evaluation

Xie et al., *OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks in Real Computer Environments* (2024).

TOM mapping:
- combine screenshot and structured accessibility observations when available,
- use executable actions,
- verify final state instead of trusting the model's claim,
- build recovery and max-step boundaries into the loop.

Reference: https://arxiv.org/abs/2404.07972

## AndroidWorld — real Android task evaluation

Rawles et al., *AndroidWorld: A Dynamic Benchmarking Environment for Autonomous Agents* (2024).

TOM mapping:
- Android-specific task initialization and success checks are a target for the test harness,
- tasks should vary parameters so the agent cannot memorize one trajectory,
- app workflows should be evaluated by resulting device state.

Reference: https://arxiv.org/abs/2405.14573

## AppAgent — smartphone interaction and app knowledge

Zhang et al., *AppAgent: Multimodal Agents as Smartphone Users* (2023).

TOM mapping:
- use a compact smartphone action vocabulary,
- support exploration of unfamiliar apps,
- accumulate reusable app interaction knowledge without requiring private backend APIs.

Reference: https://arxiv.org/abs/2312.13771

## SeeClick — visual GUI grounding

Cheng et al., *SeeClick: Harnessing GUI Grounding for Advanced Visual GUI Agents* (2024).

TOM mapping:
- keep screenshot-based grounding as a fallback when structured semantics are incomplete,
- treat target localization as a first-class problem,
- require confidence before coordinate actions.

Reference: https://arxiv.org/abs/2401.10935

## OS-ATLAS / UGround — general visual grounding

Wu et al., *OS-ATLAS: A Foundation Action Model for Generalist GUI Agents* (2024), and Gou et al., *Navigating the Digital World as Humans Do: Universal Visual Grounding for GUI Agents* (2024).

TOM mapping:
- future visual-grounding adapter should be cross-platform,
- accessibility/DOM semantics and visual grounding should be complementary,
- grounding should be trained/evaluated on diverse interfaces rather than a single app.

References:
- https://arxiv.org/abs/2410.23218
- https://arxiv.org/abs/2410.05243

## Engineering rule derived from the literature

The papers consistently show that the hard part is not producing a plausible plan; it is reliable grounding, action execution, state tracking, and evaluation. Therefore TOM treats perception, grounding, execution, verification, recovery, and safety policy as first-class runtime components rather than prompt text.
