import asyncio
import websockets
import json
import secrets
from connect4 import Connect4, PLAYER1, PLAYER2
import os
import signal

JOIN = {}
WATCH = {}

async def start(websocket):
    game = Connect4()
    connected = {websocket}

    join_key = secrets.token_urlsafe(12)
    JOIN[join_key] = game, connected
    watch_key = secrets.token_urlsafe(12)
    WATCH[watch_key] = game, connected

    try:
        event = {
            "type": "init",
            "join": join_key,
            "watch": watch_key,
        }
        await websocket.send(json.dumps(event))

        await play(websocket, game, PLAYER1, connected)

    finally:
        del JOIN[join_key]
        del WATCH[watch_key]

async def replay(websocket, game):
    for player, column, row in game.moves:
        event = {
            "type": "play",
            "player": player,
            "column": column,
            "row": row
        }
        await websocket.send(json.dumps(event))

async def watch(websocket, watch_key):
    try:
        game, connected = WATCH[watch_key]
    except KeyError:
        await error(websocket, "Game not Found")
        return

    connected.add(websocket)

    try:
        await replay(websocket, game)
        await websocket.wait_closed()
    finally:
        connected.remove(websocket)

async def error(websocket, message):
    event = {
        "type": "error",
        "message" : message
    }
    await websocket.send(json.dumps(event))

async def join(websocket, join_key):
    try:
        game, connected = JOIN[join_key]
    except KeyError:
        await error(websocket, "Game not Found")
        return
    
    connected.add(websocket)

    try:
        await play(websocket, game, PLAYER2, connected)
    finally:
        connected.remove(websocket)

async def play(websocket, game, player, connected):
    async for message in websocket:
        data = json.loads(message)
        if game.last_player != player:
            try:
                row = game.play(player, data["column"])
            except RuntimeError as e:
                event = {
                    "type": "error",
                    "message": str(e)
                }
                await websocket.send(json.dumps(event))

            event = {
                "type": "play",
                "player": player,
                "column": data["column"],
                "row": row
            }
            websockets.broadcast(connected, json.dumps(event))

            if game.last_player_won:
                event = {
                    "type": "win",
                    "player": player,
                }
                websockets.broadcast(connected, json.dumps(event))


async def handler(websocket):
    message = await websocket.recv()
    event = json.loads(message)
    assert event["type"] == "init"

    if "join" in event:
        await join(websocket, event["join"])

    if "watch" in event:
        await watch(websocket, event["watch"])

    else:
        await start(websocket)

async def main():
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

    port = int(os.environ.get("PORT", 80801))
    async with websockets.serve(handler, "", port):
        await stop

if __name__ == "__main__":
    asyncio.run(main())