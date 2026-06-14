from __future__ import annotations

from collections import deque
from time import time

import streamlit as st


def consume(
    action: str,
    *,
    max_calls: int,
    window_seconds: int,
) -> tuple[bool, int]:
    key = f"_rate_limit_{action}"
    now = time()
    calls = deque(st.session_state.get(key, []))
    cutoff = now - window_seconds

    while calls and calls[0] < cutoff:
        calls.popleft()

    if len(calls) >= max_calls:
        wait = max(1, int(window_seconds - (now - calls[0])))
        st.session_state[key] = list(calls)
        return False, wait

    calls.append(now)
    st.session_state[key] = list(calls)
    return True, 0
