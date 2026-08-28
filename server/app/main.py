import asyncio
import contextlib
import json
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import PROTOCOL_VERSION, __version__
from .bundle import Bundle
from .inference import Decoder
from .settings import Settings
from .stream import Mode, StreamSession

log = logging.getLogger("sixthfinger.server")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bundle = Bundle(settings.bundle_dir)
        app.state.bundle = bundle
        app.state.decoder = Decoder(bundle)
        app.state.active_streams = 0
        log.info("loaded bundle %s (%d trials)", settings.bundle_dir, bundle.n_trials)
        yield

    app = FastAPI(title="Sixth-Finger BCI demo server", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        bundle: Bundle = app.state.bundle
        return {
            "status": "ok",
            "version": __version__,
            "protocol": PROTOCOL_VERSION,
            "model_sha256": bundle.manifest.model.sha256,
            "synthetic": bundle.manifest.synthetic,
            "active_streams": app.state.active_streams,
        }

    @app.get("/api/info")
    async def info() -> dict:
        m = app.state.bundle.manifest
        return {
            "version": __version__,
            "protocol": PROTOCOL_VERSION,
            "synthetic": m.synthetic,
            "source": m.source.model_dump(),
            "sfreq": m.sfreq,
            "channels": m.channels,
            "display_channels": m.display_channels,
            "classes": [c.model_dump() for c in m.classes],
            "window": m.window.model_dump(),
            "model": m.model.model_dump(),
            "n_trials": len(m.trials),
            "limits": {"max_speed": settings.max_speed, "max_streams": settings.max_streams},
        }

    @app.get("/api/trials")
    async def trials() -> list[dict]:
        m = app.state.bundle.manifest
        names = [c.name for c in m.classes]
        return [
            {
                "index": t.index,
                "uid": t.uid,
                "label": names[t.label],
                "cue_onset_s": t.cue_onset_s,
                "duration_s": round(t.n_samples / m.sfreq, 3),
            }
            for t in m.trials
        ]

    @app.websocket("/ws/stream")
    async def stream(
        websocket: WebSocket,
        mode: Annotated[Mode, Query()] = "trial",
        speed: Annotated[float, Query(gt=0)] = 1.0,
        start: Annotated[int, Query(ge=0)] = 0,
        loop: Annotated[bool, Query()] = True,
    ) -> None:
        origin = websocket.headers.get("origin")
        if "*" not in settings.allowed_origins and origin not in settings.allowed_origins:
            await websocket.close(code=1008)
            return
        if app.state.active_streams >= settings.max_streams:
            await websocket.close(code=1013)
            return

        await websocket.accept()
        app.state.active_streams += 1
        session = StreamSession(
            app.state.bundle,
            app.state.decoder,
            mode=mode,
            speed=speed,
            start_trial=start,
            loop=loop,
            chunk_samples=settings.chunk_samples,
            hop_seconds=settings.hop_seconds,
            max_speed=settings.max_speed,
        )

        async def send(message: dict) -> None:
            await websocket.send_text(json.dumps(message, separators=(",", ":")))

        async def read_controls() -> None:
            while True:
                raw = await websocket.receive_text()
                try:
                    reply = session.handle_control(json.loads(raw))
                except (ValueError, TypeError):
                    reply = {"type": "error", "message": "control messages must be JSON objects"}
                if reply is not None:
                    await send(reply)

        producer = asyncio.create_task(session.run(send))
        consumer = asyncio.create_task(read_controls())
        try:
            done, _ = await asyncio.wait({producer, consumer}, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.exception() and not isinstance(task.exception(), WebSocketDisconnect):
                    log.error("stream failed", exc_info=task.exception())
        finally:
            for task in (producer, consumer):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                    await task
            app.state.active_streams -= 1
            with contextlib.suppress(RuntimeError):
                await websocket.close()

    return app


app = create_app()
