import pytest

from tom.execution.recovery_loop import PostActionRecoveryLoop, RecoveryDecision, RecoveryPolicy
from tom.perception.multimodal_observation import MultimodalObservation


def obs(i: str):
    return MultimodalObservation.now(i, "com.example.app")


@pytest.mark.asyncio
async def test_verifies_after_action():
    loop = PostActionRecoveryLoop(policy=RecoveryPolicy(max_retries=1, max_total_attempts=2))
    calls = []

    async def execute(n): calls.append(("execute", n))
    async def observe(n): return obs(f"after-{n}")
    async def request(msg): calls.append(("ask", msg))
    async def reground(n, observation): return True

    result = await loop.run(obs("before"), execute, observe, lambda _: True, reground, request)
    assert result.decision is RecoveryDecision.VERIFIED
    assert result.attempts == 1


@pytest.mark.asyncio
async def test_missing_observation_never_retries_blindly():
    loop = PostActionRecoveryLoop()
    executed = []

    async def execute(n): executed.append(n)
    async def observe(n): return None
    async def request(msg): pass
    async def reground(n, observation): return True

    result = await loop.run(obs("before"), execute, observe, lambda _: True, reground, request)
    assert result.decision is RecoveryDecision.ASK_USER
    assert executed == [1]


@pytest.mark.asyncio
async def test_reground_then_retry_is_bounded():
    loop = PostActionRecoveryLoop(policy=RecoveryPolicy(max_retries=1, max_total_attempts=2))
    executed = []

    async def execute(n): executed.append(n)
    async def observe(n): return obs(f"after-{n}")
    async def request(msg): pass
    async def reground(n, observation): return True

    result = await loop.run(obs("before"), execute, observe, lambda o: o.observation_id == "after-2", reground, request)
    assert result.decision is RecoveryDecision.VERIFIED
    assert executed == [1, 2]
