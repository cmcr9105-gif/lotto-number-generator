
from __future__ import annotations
import hashlib

def birth_based_weights(birth_text: str):
    key = (birth_text or "").strip().encode("utf-8")
    h = hashlib.sha256(key).digest()
    weights = {}
    for n in range(1,46):
        b = h[(n-1) % len(h)]
        weights[n] = 0.90 + (b / 255.0) * 0.20
    return weights

def favorite_numbers_from_birth(birth_text: str, count=6):
    w = birth_based_weights(birth_text)
    return [n for n,_ in sorted(w.items(), key=lambda x:(-x[1], x[0]))[:count]]
