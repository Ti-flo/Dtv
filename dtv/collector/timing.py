"""
Human-like timing utilities.

Ankama's anti-bot detects perfectly regular timing. All delays should use
these helpers instead of bare time.sleep() to add natural variance.
"""
import logging
import random
import time

log = logging.getLogger(__name__)


def human_delay(min_s: float, max_s: float):
    """Sleep for a uniformly random duration between min_s and max_s."""
    duration = random.uniform(min_s, max_s)
    log.debug("delay %.2fs", duration)
    time.sleep(duration)


def jitter(base_s: float, variance: float = 0.3) -> float:
    """
    Return base_s ± up to variance*100% (default ±30%), clamped to >= 0.1s.

    Usage:
        time.sleep(jitter(2.0))  # sleeps 1.4s – 2.6s
    """
    delta = base_s * variance
    return max(0.1, base_s + random.uniform(-delta, delta))
