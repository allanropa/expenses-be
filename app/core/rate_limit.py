from collections import defaultdict, deque
from threading import Lock
from time import monotonic


WINDOW_SECONDS = 15 * 60
MAX_FAILURES = 10
_failures: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def _key(ip: str, email: str) -> str:
    return f"{ip}:{email.lower()}"


def check_login_allowed(ip: str, email: str) -> bool:
    now = monotonic()
    key = _key(ip, email)
    with _lock:
        attempts = _failures[key]
        while attempts and now - attempts[0] >= WINDOW_SECONDS:
            attempts.popleft()
        return len(attempts) < MAX_FAILURES


def record_login_failure(ip: str, email: str) -> None:
    now = monotonic()
    key = _key(ip, email)
    with _lock:
        attempts = _failures[key]
        while attempts and now - attempts[0] >= WINDOW_SECONDS:
            attempts.popleft()
        attempts.append(now)


def clear_login_failures(ip: str, email: str) -> None:
    with _lock:
        _failures.pop(_key(ip, email), None)
