"""TOM's open-source-first expressive voice stack.

The package separates perception, conversation intent, emotional direction,
voice identity, expressive prosody, turn-taking, and synthesis. A model
adapter must be installed/configured; there is no fake audio fallback.
"""

from .director import VoiceDirector
from .engine import SpeechEngine, SpeechEngineConfig
from .models import Emotion, Language, VoiceProfile, VoiceStyle
from .prosody import ExpressiveSpeechPlanner, PCM16ProsodyExtractor
from .turntaking import DuplexState, DuplexTurnManager, TurnDecision, TurnSignal

__all__ = [
    "Emotion",
    "Language",
    "SpeechEngine",
    "SpeechEngineConfig",
    "VoiceDirector",
    "VoiceProfile",
    "VoiceStyle",
    "ExpressiveSpeechPlanner",
    "PCM16ProsodyExtractor",
    "DuplexState",
    "DuplexTurnManager",
    "TurnDecision",
    "TurnSignal",
]
