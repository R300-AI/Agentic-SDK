from __future__ import annotations

import argparse
import os

import uvicorn
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.middleware.wsgi import WSGIMiddleware

from playground.app import create_app


_WORKER_SETTINGS = ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS")


def require_single_process(environment: "dict[str, str] | None" = None) -> None:
    """Refuse to start where interruption would silently stop working.

    An interjection cancels a workflow by setting a flag the running workflow
    can see, which only holds inside one process. Add workers and the request
    to stop lands in a different one: the agent keeps talking, and nothing
    anywhere reports an error.

    Raising here is the point. A voice agent that has quietly lost the ability
    to be interrupted looks exactly like one that works.
    """
    values = os.environ if environment is None else environment
    for setting in _WORKER_SETTINGS:
        raw = str(values.get(setting) or "").strip()
        if not raw:
            continue
        try:
            workers = int(raw)
        except ValueError:
            continue
        if workers > 1:
            raise RuntimeError(
                f"{setting}={workers} 會讓插話功能靜默失效。中斷訊號必須和它要停止的"
                f"工作流在同一個行程，多個 worker 時訊號會落在別的行程，agent 會繼續"
                f"講而且不會有任何錯誤。請把 {setting} 設為 1，或移除它。"
            )


app = FastAPI(title="Agentic SDK Playground")


@app.websocket("/playground/voice/{session_id}")
async def voice_session(socket: WebSocket, session_id: str) -> None:
    """Carry microphone audio, and carry interjections back the other way.

    Mounted here rather than inside the Flask app because this is the layer
    that speaks websocket. The browser never sees a credential: it talks to
    this endpoint, and this endpoint talks to the speech service.
    """
    import asyncio

    from playground.services import voice_session
    from playground.services.voice_session import registry, unknown_session_message

    await socket.accept()
    await socket.send_json({"type": "session.opened", "session_id": session_id})

    loop = asyncio.get_running_loop()
    listener = None

    async def stream_speech(text: str) -> None:
        voice = voice_session.open_synthesis()
        if voice is None:
            await socket.send_json(
                {"type": "unavailable", "message": voice_session.speech_unavailable_message()}
            )
            return
        token = registry.token(session_id)
        pieces = voice.speak(text)
        while True:
            # Pulled on a thread, because each piece is a wait on the service —
            # and waiting here would stop this socket reading its microphone.
            # Measured against the deployment, someone speaking over the answer
            # waited 3.8 seconds to be heard; speaking with nothing playing was
            # heard in 0.05.
            piece = await asyncio.to_thread(next, pieces, None)
            if piece is None:
                break
            if token is not None and token.cancelled:
                # Abandoning the iterator stops the synthesis too: the rest of
                # a sentence nobody will hear is not worth generating, let
                # alone paying for.
                pieces.close()
                break
            await socket.send_bytes(piece)
        await socket.send_json({"type": "spoken"})

    # Registered so the running answer can start playing the moment its spoken
    # half exists, instead of waiting for the page to ask once it is finished.
    registry.attach_speaker(
        session_id,
        lambda text: asyncio.run_coroutine_threadsafe(stream_speech(text), loop),
    )

    def announce(payload: dict) -> None:
        # Called from the transcription session's own thread, which is not the
        # one the socket belongs to.
        asyncio.run_coroutine_threadsafe(socket.send_json(payload), loop)

    def began_speaking() -> None:
        # The interruption signal. Waiting for the words instead would mean
        # talking over the person for the three seconds a transcript takes.
        #
        # The page is told first: stopping the playback is what the person
        # feels, and it is a decision the browser can make without asking. Its
        # reply carries the one thing only it knows — how much was played —
        # and refines this cancellation, which cannot know and says so.
        announce({"type": "speech_started"})
        registry.interject(session_id, heard_seconds=None)

    try:
        while True:
            message = await socket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if (audio := message.get("bytes")) is not None:
                if listener is None:
                    transport = voice_session.open_transcription()
                    if transport is None:
                        await socket.send_json(
                            {
                                "type": "unavailable",
                                "message": voice_session.speech_unavailable_message(),
                            }
                        )
                        continue
                    listener = registry.listen(session_id, transport)
                    transport.on_speech_started(began_speaking)
                    transport.on_transcript(
                        lambda text: announce({"type": "transcript", "text": text})
                    )
                if listener.hear(audio):
                    await socket.send_json({"type": "listening"})
                continue
            message = json.loads(message.get("text") or "{}")
            kind = str(message.get("type") or "")
            if kind == "interject":
                # The browser is the only place that knows how long the person
                # actually listened, because it is the thing that was playing.
                reported = message.get("heard_seconds")
                heard = None if reported is None else float(reported)
                if registry.interject(session_id, heard_seconds=heard):
                    await socket.send_json({"type": "interjected", "heard_seconds": heard})
                else:
                    await socket.send_json(
                        {"type": "nothing_to_interrupt", "message": unknown_session_message()}
                    )
            elif kind == "speak":
                await stream_speech(str(message.get("text") or ""))
            elif kind == "close":
                break
    except WebSocketDisconnect:
        pass
    finally:
        # Leaving the page ends the session. A registry that only grows is a
        # leak in a process that is meant to stay up.
        registry.close(session_id)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# At import, not in main(): `gunicorn -w 4 playground.main:app` never calls
# main(), and that is the launcher most likely to add workers.
require_single_process()

app.mount("/", WSGIMiddleware(create_app()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Agentic SDK Playground web app.")
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", os.environ.get("WEBSITES_PORT", "80"))))
    args = parser.parse_args()

    uvicorn.run(
        "playground.main:app",
        host=args.host,
        port=args.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()