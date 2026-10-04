"""Offline serialized reducer owner: durable inputs first, then state and outputs."""

from dataclasses import dataclass
from threading import Lock

from quant_research.serde import InputError
from .domain import Event, parse_event
from .engine import EngineState, apply_event
from .journal import Journal, _validated_config


@dataclass(frozen=True)
class ReplayResult:
    state: EngineState
    outputs: tuple[dict, ...]


def replay(events, config):
    """Pure historical reconstruction; does not restart or resend any submission."""
    config = _validated_config(config)
    state = EngineState.initial(config)
    outputs = []
    for event in events:
        event = parse_event(event.raw) if isinstance(event, Event) else parse_event(event)
        transition = apply_event(state, event, config)
        state = transition.state
        outputs.extend(transition.outputs)
    return ReplayResult(state, tuple(outputs))


class OfflineRuntime:
    def __init__(self, path, config, *, restart_time_ms=None):
        self.config = _validated_config(config)
        self.poisoned = False
        self._lock = Lock()
        self.journal = Journal(path, self.config)
        self.startup_outputs = ()
        try:
            historical = replay(self.journal.events, self.config)
            self.state = historical.state
            if self.journal.existing:
                now = self.state.last_time_ms if restart_time_ms is None else restart_time_ms
                restart = parse_event({'sequence': self.state.last_sequence + 1,
                                       'time_ms': now, 'kind': 'restart', 'payload': {}})
                self.startup_outputs = self.process(restart).outputs
        except BaseException:
            self.journal.close()
            raise

    def process(self, event):
        with self._lock:
            return self._process(event)

    def _process(self, event):
        if self.poisoned or self.journal.poisoned:
            raise InputError('control runtime is poisoned; close and recover explicitly')
        event = parse_event(event.raw) if isinstance(event, Event) else parse_event(event)
        if event.sequence != self.state.last_sequence + 1 or event.time_ms < self.state.last_time_ms:
            raise InputError('control event sequence or clock regression')
        try:
            self.journal.append(event)
            transition = apply_event(self.state, event, self.config)
            self.state = transition.state
            return transition
        except BaseException:
            # An input may already be durable. Continuing the old state is unsafe.
            self.poisoned = True
            raise

    def close(self):
        self.journal.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
