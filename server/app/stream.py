"""Replays held-out trials as if they were being recorded, and decodes them."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from . import PROTOCOL_VERSION, __version__
from .bundle import Bundle, TrialInfo, Window
from .gate import CommandGate
from .inference import Decoder

Message = dict[str, Any]
Send = Callable[[Message], Awaitable[None]]
Mode = Literal["trial", "continuous"]


@dataclass(frozen=True)
class TimelineEvent:
    sample: int
    kind: Literal["phase", "decode"]
    phase: str | None = None
    window: str | None = None
    start: int = 0
    stop: int = 0


def trial_timeline(trial: TrialInfo, sfreq: float, window: Window) -> list[TimelineEvent]:
    """Phase changes and decode points of one trial, in samples from the rest onset.

    The rest window is cut from the fixation period and the imagery window from
    the cue onset, both [window.start_s, window.end_s), exactly as in training.
    A window is decoded the moment its last sample has arrived.
    """
    cue = round(trial.cue_onset_s * sfreq)
    w0, w1 = round(window.start_s * sfreq), round(window.end_s * sfreq)
    if cue + w1 > trial.n_samples:
        raise ValueError(f"trial {trial.uid} ends before its imagery window")
    events = [
        TimelineEvent(0, "phase", phase="rest"),
        TimelineEvent(max(cue - round(sfreq), 0), "phase", phase="prepare"),
        TimelineEvent(cue, "phase", phase="imagery"),
        TimelineEvent(w1, "decode", window="rest", start=w0, stop=w1),
        TimelineEvent(cue + w1, "decode", window="imagery", start=cue + w0, stop=cue + w1),
    ]
    return sorted(events, key=lambda e: (e.sample, e.kind != "phase"))


class PacingClock:
    """Maps seconds of streamed data to wall-clock time, with pause and speed."""

    def __init__(self, speed: float) -> None:
        self._loop = asyncio.get_running_loop()
        self.speed = speed
        self._anchor_wall = self._loop.time()
        self._anchor_data = 0.0
        self._resumed = asyncio.Event()
        self._resumed.set()
        self.data_time = 0.0

    @property
    def paused(self) -> bool:
        return not self._resumed.is_set()

    def _reanchor(self) -> None:
        self._anchor_wall = self._loop.time()
        self._anchor_data = self.data_time

    def set_speed(self, speed: float) -> None:
        self._reanchor()
        self.speed = speed

    def pause(self) -> None:
        self._resumed.clear()

    def resume(self) -> None:
        self._reanchor()
        self._resumed.set()

    async def wait_until(self, data_time: float) -> None:
        await self._resumed.wait()
        delay = self._anchor_wall + (data_time - self._anchor_data) / self.speed - self._loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        self.data_time = data_time


class StreamSession:
    def __init__(
        self,
        bundle: Bundle,
        decoder: Decoder,
        mode: Mode = "trial",
        speed: float = 1.0,
        start_trial: int = 0,
        loop: bool = True,
        chunk_samples: int = 20,
        hop_seconds: float = 0.5,
        max_speed: float = 8.0,
    ) -> None:
        self.bundle = bundle
        self.decoder = decoder
        self.mode = mode
        self.max_speed = max_speed
        self.initial_speed = self._clamp(speed)
        self.trial_index = start_trial % bundle.n_trials
        self.loop = loop
        self.chunk = chunk_samples
        m = bundle.manifest
        self.sfreq = m.sfreq
        self.hop = round(hop_seconds * self.sfreq)
        self.display_idx = bundle.display_indices()
        self.decimation = m.display_decimation
        self.class_names = [c.name for c in m.classes]
        self.commands = [c.command for c in m.classes]
        self.gate = CommandGate(n_classes=len(m.classes))
        self._jump_to: int | None = None
        self._clock: PacingClock | None = None
        self._history = np.zeros((len(m.channels), 0), dtype=np.float32)

    def _clamp(self, speed: float) -> float:
        return float(min(max(speed, 0.25), self.max_speed))

    def hello(self) -> Message:
        m = self.bundle.manifest
        return {
            "type": "hello",
            "protocol": PROTOCOL_VERSION,
            "server_version": __version__,
            "mode": self.mode,
            "speed": self.initial_speed,
            "n_trials": self.bundle.n_trials,
            "sfreq": self.sfreq,
            "display_sfreq": self.sfreq / self.decimation,
            "display_channels": m.display_channels,
            "classes": [c.model_dump() for c in m.classes],
            "window": m.window.model_dump(),
            "synthetic": m.synthetic,
            "model": {"name": m.model.name, "method": m.model.method, "sha256": m.model.sha256},
        }

    def handle_control(self, message: Message) -> Message | None:
        kind = message.get("type")
        clock = self._clock
        if clock is None:
            return None
        if kind == "pause":
            clock.pause()
        elif kind == "resume":
            clock.resume()
        elif kind == "speed":
            clock.set_speed(self._clamp(float(message.get("value", 1.0))))
        elif kind == "jump":
            self._jump_to = int(message.get("trial", 0)) % self.bundle.n_trials
            clock.resume()
        else:
            return {"type": "error", "message": f"unknown control message {kind!r}"}
        return {"type": "status", "paused": clock.paused, "speed": clock.speed}

    def _prediction(
        self,
        trial: int,
        t: float,
        window: str,
        data: np.ndarray,
        truth: str | None,
        span: tuple[int, int],
    ) -> Message:
        probs, latency = self.decoder.predict(data)
        label_id = int(np.argmax(probs))
        message: Message = {
            "type": "prediction",
            "trial": trial,
            "t": round(t, 3),
            "window": window,
            "window_s": [round(span[0] / self.sfreq, 3), round(span[1] / self.sfreq, 3)],
            "probs": [round(float(p), 5) for p in probs],
            "label_id": label_id,
            "label": self.class_names[label_id],
            "command": self.commands[label_id],
            "confidence": round(float(probs[label_id]), 5),
            "truth": truth,
            "correct": None if truth is None else self.class_names[label_id] == truth,
            "latency_ms": round(latency, 3),
            "source": "server",
        }
        if self.mode == "continuous":
            active = self.gate.update(probs)
            message.update(
                smoothed=[round(float(p), 5) for p in self.gate.smoothed],
                command=self.commands[active],
                experimental=True,
            )
        return message

    async def run(self, send: Send) -> None:
        self._clock = PacingClock(self.initial_speed)
        await send(self.hello())
        passes = 0
        while True:
            index = self.trial_index
            finished = await self._stream_trial(index, passes, send)
            if self._jump_to is not None:
                self.trial_index, self._jump_to = self._jump_to, None
                continue
            if not finished:
                return
            self.trial_index = (index + 1) % self.bundle.n_trials
            if self.trial_index == 0:
                passes += 1
                if not self.loop:
                    await send({"type": "end", "n_trials": self.bundle.n_trials})
                    return

    async def _stream_trial(self, index: int, passes: int, send: Send) -> bool:
        clock = self._clock
        assert clock is not None
        info = self.bundle.manifest.trials[index]
        data = self.bundle.trial_data(index)
        truth_name = self.class_names[info.label]
        cue = round(info.cue_onset_s * self.sfreq)
        events = trial_timeline(info, self.sfreq, self.bundle.manifest.window)
        context = np.concatenate([self._history, data], axis=1)
        offset = self._history.shape[1]
        base_time = clock.data_time

        await send(
            {
                "type": "trial_start",
                "trial": index,
                "pass": passes,
                "uid": info.uid,
                "n_samples": info.n_samples,
                "duration_s": round(info.n_samples / self.sfreq, 3),
                "cue_onset_s": info.cue_onset_s,
            }
        )
        next_event = 0
        pos = 0
        while pos < info.n_samples:
            while next_event < len(events) and events[next_event].sample <= pos:
                await self._emit_event(events[next_event], index, data, truth_name, send)
                next_event += 1
            stop = min(pos + self.chunk, info.n_samples)
            await clock.wait_until(base_time + stop / self.sfreq)
            if self._jump_to is not None:
                return True
            chunk = data[self.display_idx, pos : stop : self.decimation]
            await send(
                {
                    "type": "eeg",
                    "trial": index,
                    "t": round(pos / self.sfreq, 3),
                    "data": np.round(chunk, 2).tolist(),
                }
            )
            if self.mode == "continuous":
                for end in range(pos + 1, stop + 1):
                    if end % self.hop == 0 and offset + end >= self.decoder.n_times:
                        window = context[:, offset + end - self.decoder.n_times : offset + end]
                        centre = end - self.decoder.n_times // 2
                        truth = truth_name if centre >= cue else self.class_names[0]
                        span = (end - self.decoder.n_times, end)
                        await send(
                            self._prediction(
                                index, end / self.sfreq, "sliding", window, truth, span
                            )
                        )
            pos = stop
        while next_event < len(events):
            await self._emit_event(events[next_event], index, data, truth_name, send)
            next_event += 1
        await send({"type": "trial_end", "trial": index})
        self._history = data[:, -self.decoder.n_times :]
        return True

    async def _emit_event(
        self, event: TimelineEvent, index: int, data: np.ndarray, truth_name: str, send: Send
    ) -> None:
        t = event.sample / self.sfreq
        if event.kind == "phase":
            truth = {"rest": self.class_names[0], "prepare": None, "imagery": truth_name}[
                event.phase
            ]
            await send(
                {
                    "type": "phase",
                    "trial": index,
                    "t": round(t, 3),
                    "phase": event.phase,
                    "truth": truth,
                }
            )
        elif self.mode == "trial":
            truth = self.class_names[0] if event.window == "rest" else truth_name
            window = data[:, event.start : event.stop]
            await send(
                self._prediction(index, t, event.window, window, truth, (event.start, event.stop))
            )
