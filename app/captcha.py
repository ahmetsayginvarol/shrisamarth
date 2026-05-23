import random
import secrets
import time

_store: dict = {}  # token -> {answer, expires}


def _clean_store():
    now = time.time()
    expired = [k for k, v in _store.items() if v['expires'] < now]
    for k in expired:
        del _store[k]


def generate_captcha():
    """Return (token, question_string). Token maps to correct answer in server-side store."""
    _clean_store()
    a = random.randint(2, 15)
    b = random.randint(2, 15)
    op = random.choice(['+', '-', '×'])
    if op == '+':
        answer = a + b
    elif op == '-':
        a, b = max(a, b), min(a, b)
        answer = a - b
    else:
        answer = a * b

    token = secrets.token_hex(16)
    _store[token] = {'answer': answer, 'expires': time.time() + 600}
    return token, f"{a} {op} {b} = ?"


def verify_captcha(token: str, submitted) -> bool:
    """Verify and consume a captcha token. Returns True if correct."""
    if not token or token not in _store:
        return False
    entry = _store[token]
    if time.time() > entry['expires']:
        del _store[token]
        return False
    correct = str(entry['answer']).strip() == str(submitted or '').strip()
    del _store[token]  # single use
    return correct
