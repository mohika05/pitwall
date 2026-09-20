import asyncio
import json

import httpx
import websockets


API_BASE = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws/replay/9896"

SESSION_KEY = 9896


async def main() -> None:
    async with httpx.AsyncClient(
        base_url=API_BASE,
        timeout=10.0,
    ) as client:

        # Start from a known state.
        response = await client.post(
            f"/replay/{SESSION_KEY}/reset"
        )
        response.raise_for_status()

        response = await client.post(
            f"/replay/{SESSION_KEY}/speed",
            json={
                "speed": 100
            },
        )
        response.raise_for_status()

        async with websockets.connect(
            WS_URL
        ) as websocket:

            # ---------------------------------------------
            # INITIAL STATE
            # ---------------------------------------------

            raw = await asyncio.wait_for(
                websocket.recv(),
                timeout=5,
            )

            initial = json.loads(
                raw
            )

            assert (
                initial["type"]
                == "race_state"
            )

            print(
                "Initial message:"
            )

            print(
                "  event index:",
                initial["payload"][
                    "event_index"
                ],
            )

            print(
                "  total events:",
                initial["payload"][
                    "total_events"
                ],
            )

            print(
                "  lap:",
                initial["payload"][
                    "state"
                ]["current_lap"],
            )

            # ---------------------------------------------
            # START REPLAY
            # ---------------------------------------------

            response = await client.post(
                f"/replay/{SESSION_KEY}/play"
            )

            response.raise_for_status()

            print()
            print(
                "Replay started."
            )

            # Receive a few realtime state updates.
            updates_received = 0

            last_index = -1

            while updates_received < 5:
                raw = (
                    await asyncio.wait_for(
                        websocket.recv(),
                        timeout=10,
                    )
                )

                message = json.loads(
                    raw
                )

                if (
                    message.get("type")
                    != "race_state"
                ):
                    continue

                payload = (
                    message["payload"]
                )

                state = (
                    payload["state"]
                )

                event_index = (
                    payload["event_index"]
                )

                print(
                    f"Update "
                    f"{updates_received + 1}: "
                    f"event={event_index}, "
                    f"lap="
                    f"{state['current_lap']}, "
                    f"time="
                    f"{state['replay_timestamp']}"
                )

                if event_index < last_index:
                    raise RuntimeError(
                        (
                            "WebSocket event "
                            "index moved backwards"
                        )
                    )

                last_index = (
                    event_index
                )

                updates_received += 1

            # ---------------------------------------------
            # PAUSE
            # ---------------------------------------------

            response = await client.post(
                f"/replay/{SESSION_KEY}/pause"
            )

            response.raise_for_status()

            print()
            print(
                "Replay paused."
            )

            # ---------------------------------------------
            # PING / PONG
            # ---------------------------------------------

            await websocket.send(
                "ping"
            )

            while True:
                raw = (
                    await asyncio.wait_for(
                        websocket.recv(),
                        timeout=5,
                    )
                )

                message = json.loads(
                    raw
                )

                if (
                    message.get("type")
                    == "pong"
                ):
                    break

            print(
                "WebSocket ping/pong: PASS"
            )

            # ---------------------------------------------
            # CLEANUP
            # ---------------------------------------------

            response = await client.post(
                f"/replay/{SESSION_KEY}/reset"
            )

            response.raise_for_status()

            print(
                "Replay reset: PASS"
            )

            print()
            print(
                "REALTIME TEST: PASS"
            )


if __name__ == "__main__":
    asyncio.run(
        main()
    )