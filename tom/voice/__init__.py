"""TOM's open-source-first expressive voice stack.

The package deliberately separates conversation intent, emotional direction,
voice identity, and synthesis. A model adapter must be installed/configured;
there is no fake audio fallback.
"""

from .director import VoiceDirector
from .engine import SpeechEngine, SpeechEngineConfig
from .models import Emotion, Language, VoiceProfile, VoiceStyle

__all__ = [
    "Emotion",
    "Language",
    "SpeechEngine",
    "SpeechEngineConfig",
    "VoiceDirector",
    "VoiceProfile",
    "VoiceStyle",
]
