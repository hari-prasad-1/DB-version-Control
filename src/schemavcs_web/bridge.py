"""Turns a blocking, synchronous confirm callback into a pausable one, so a
web request/response cycle can drive `merge()`/`detect_renames()` one click
at a time without either engine function knowing anything changed.

Both functions call their `confirm` argument inline, once per question,
blocking until it returns -- there's no way to ask them "give me question 1,
let me show it in a browser, come back later for question 2." This bridge
runs the real, unmodified engine call on a background thread; `ask()` -- the
confirm callback itself -- blocks THAT thread on an event, never the HTTP
request thread. An HTTP GET just reads whatever `ask()` most recently
stashed; an HTTP POST answers it and lets the worker thread continue.

A multi-pass "replay with placeholder answers, then re-run for real" design
was considered instead: it changes only the call site, not the engine, and
needs no threading. It falls apart on `detect_renames()` specifically --
its candidate pool shrinks on every accept, so proposal N+1's identity
depends on the real answer to proposal N (see `rename_detect/detector.py`,
the `remaining_old`/`remaining_new` pools in the confirm loop). No fixed
placeholder answer reproduces the real proposal sequence once a real answer
diverges from it, so the only correctness-preserving version of that
approach is re-running the whole function from scratch on every click --
workable, but that's simulating a pause by brute-force re-execution, not
actually pausing. `merge()`'s own conflict list happens to be answer-
independent today (built once, before its loop starts), so the replay
approach would work there -- but relying on that staying true forever, for
only one of the two functions, was worse than one uniform mechanism that
doesn't care either way.
"""

import threading
from collections.abc import Callable
from typing import Generic, TypeVar

Q = TypeVar("Q")
A = TypeVar("A")


class BridgeError(Exception):
    """Raised by `result()`/`poll_question()` when the bridge is used out of
    the only valid sequence: run_in_background -> repeated
    (poll_question, submit_answer) -> result."""


class WebConfirmBridge(Generic[Q, A]):
    """One instance per in-flight merge/rename session. `ask` is passed
    directly as the engine's `confirm` callback -- it IS a `ConfirmFn`, not
    a wrapper that calls one."""

    def __init__(self) -> None:
        self._question_ready = threading.Event()
        self._answer_ready = threading.Event()
        self._done = threading.Event()
        self._started = False
        self._question: Q | None = None
        self._answer: A | None = None
        self._error: BaseException | None = None
        self._result: object = None

    def ask(self, question: Q) -> A:
        """The confirm callback. Runs on the worker thread, inside the real
        merge()/detect_renames() call stack -- blocks that thread only."""
        self._question = question
        self._answer_ready.clear()
        self._question_ready.set()
        self._answer_ready.wait()
        self._question_ready.clear()
        assert self._answer is not None  # set by submit_answer before the event fires
        return self._answer

    def run_in_background(self, target: Callable[[], object]) -> None:
        if self._started:
            raise BridgeError("this bridge has already been started")
        self._started = True
        thread = threading.Thread(target=self._run, args=(target,), daemon=True)
        thread.start()

    def _run(self, target: Callable[[], object]) -> None:
        try:
            self._result = target()
        except BaseException as exc:  # noqa: BLE001 -- must surface to result(), not swallow
            self._error = exc
        finally:
            # Set done BEFORE waking poll_question(), so a poller that was
            # blocked waiting for a question that will never come (the
            # worker finished with zero remaining questions) sees `is_done`
            # true rather than racing to read a stale `self._question`.
            self._done.set()
            self._question_ready.set()

    def poll_question(self, timeout: float = 5.0) -> Q | None:
        """Returns the current pending question, or None if the worker is
        done (call `result()` next) or hasn't produced one within the
        timeout (caller should poll again)."""
        if not self._started:
            raise BridgeError("run_in_background() must be called before poll_question()")
        fired = self._question_ready.wait(timeout)
        if not fired or self._done.is_set():
            return None
        return self._question

    def submit_answer(self, answer: A) -> None:
        if self._done.is_set():
            raise BridgeError("the worker has already finished; nothing left to answer")
        self._answer = answer
        self._question_ready.clear()
        self._answer_ready.set()

    def result(self) -> object:
        """Blocks until the worker finishes, then returns its return value
        or re-raises whatever it raised."""
        self._done.wait()
        if self._error is not None:
            raise self._error
        return self._result

    def is_done(self) -> bool:
        return self._done.is_set()
