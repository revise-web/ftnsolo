#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mini 1v1 build-fight – WebSocket + fichiers statiques
Bind 0.0.0.0 et port donné par Render via $PORT
"""
import asyncio, json, time, random, math, pathlib, os
import aiohttp
import aiohttp_cors
from aiohttp import web
import websockets
from websockets.server import serve as ws_serve

# ---------- config ----------
MAP    = 50
TO_WIN = 10
WOOD, STONE, METAL = 150, 200, 250
STATIC_DIR = pathlib.Path(__file__).with_name("static")

# ---------- joueur ----------
class Player:
    def __init__(self, pid):
        self.pid = pid
        self.x, self.y, self.z = random.uniform(-MAP/2, MAP/2), 1.0, random.uniform(-MAP/2, MAP/2)
        self.yaw = self.pitch = 0
        self.hp = self.shield = 100
        self.kills = 0
        self.mats = {"wood": 999, "stone": 999, "metal": 999}
        self.weapons = {"ar": 30, "shotgun": 5, "smg": 25}
        self.state = "alive"
        self.respawn_t = 0

# ---------- game ----------
class GameSrv:
    def __init__(self):
        self.p = {}          # pid -> Player
        self.structs = []
        self.bullets = []
        self.ws_map = {}     # websocket -> pid

    # ---- reset ----
    def reset(self, pl):
        pl.x, pl.y, pl.z = random.uniform(-MAP/2, MAP/2), 1.0, random.uniform(-MAP/2, MAP/2)
        pl.hp = pl.shield = 100
        pl.weapons = {"ar": 30, "shotgun": 5, "smg": 25}
        pl.state = "alive"

    # ---- raycast ----
    def raycast(self, x, y, z, dx, dy, dz, maxd=100):
        step = 0.2
        for _ in range(int(maxd / step)):
            x += dx * step; y += dy * step; z += dz * step
            if y <= 0:
                return None, None, (x, 0, z)
            # joueur
            for p in self.p.values():
                if p.state == "alive" and math.dist((x, z), (p.x, p.z)) < 1 and abs(y - p.y) < 1.5:
                    return p, None, (x, y, z)
            # structure
            for s in self.structs:
                sx, sy, sz = s["x"], s["y"], s["z"]
                if abs(x - sx) < .7 and abs(y - sy) < .7 and abs(z - sz) < .7:
                    return None, s, (x, y, z)
        return None, None, (x, y, z)

    # ---- update 30 Hz ----
    def update(self, dt):
        for b in self.bullets[:]:
            b["x"] += b["dx"] * dt * 50
            b["y"] += b["dy"] * dt * 50
            b["z"] += b["dz"] * dt * 50
            hitP, hitS, _ = self.raycast(b["x"], b["y"], b["z"], b["dx"], b["dy"], b["dz"], 2)
            if hitP or hitS or b["y"] <= 0:
                if hitP and hitP.pid != b["pid"]:
                    dmg = 30 if b["w"] == "shotgun" else (20 if b["w"] == "ar" else 15)
                    if hitP.shield > 0:
                        hitP.shield = max(0, hitP.shield - dmg)
                    else:
                        hitP.hp -= dmg
                    if hitP.hp <= 0 and hitP.state == "alive":
                        hitP.state = "dead"
                        killer = self.p[b["pid"]]
                        killer.kills += 1
                        self.broadcast({"t": "kill", "killer": killer.pid, "killed": hitP.pid})
                        if killer.kills >= TO_WIN:
                            self.broadcast({"t": "end", "winner": killer.pid})
                if hitS:
                    hitS["hp"] -= 20
                    if hitS["hp"] <= 0:
                        self.structs.remove(hitS)
                self.bullets.remove(b)
        # respawn
        for p in self.p.values():
            if p.state == "dead" and time.time() - p.respawn_t > .1:
                self.reset(p)

    # ---- broadcast ----
    def broadcast(self, msg):
        dead = []
        for ws, _ in list(self.ws_map.items()):
            try:
                asyncio.create_task(ws.send(json.dumps(msg)))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def disconnect(self, ws):
        pid = self.ws_map.pop(ws, None)
        if pid:
            self.p.pop(pid, None)
            print("Player", pid, "déconnecté")

    # ---- websocket ----
    async def ws_handler(self, ws, path):
        pid = 1 if 1 not in self.p else 2
        if len(self.p) >= 2 and pid not in self.p:
            await ws.send(json.dumps({"t": "full"})); return
        pl = Player(pid)
        self.p[pid] = pl
        self.ws_map[ws] = pid
        await ws.send(json.dumps({"t": "id", "pid": pid}))
        self.broadcast({"t": "join", "pid": pid})
        try:
            async for raw in ws:
                data = json.loads(raw)
                t = data["t"]
                if t == "move":
                    pl.x, pl.y, pl.z = data["x"], data["y"], data["z"]
                    pl.yaw, pl.pitch = data["yaw"], data["pitch"]
                elif t == "shoot":
                    self.bullets.append({"x": pl.x, "y": pl.y + 1.5, "z": pl.z,
                                         "dx": data["dx"], "dy": data["dy"], "dz": data["dz"],
                                         "w": data["w"], "pid": pl.pid})
                elif t == "build":
                    self.structs.append({"x": data["x"], "y": data["y"], "z": data["z"],
                                         "type": data["mat"],
                                         "hp": {"wood": WOOD, "stone": STONE, "metal": METAL}[data["mat"]]})
                elif t == "edit":
                    for s in self.structs[:]:
                        if math.dist((s["x"], s["z"]), (data["x"], data["z"])) < 1:
                            self.structs.remove(s); break
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.disconnect(ws)

    # ---- ticker 30 Hz ----
    async def ticker(self):
        last = time.time()
        while True:
            await asyncio.sleep(1 / 30)
            now = time.time(); dt = now - last; last = now
            self.update(dt)
            snap = {"t": "snap",
                    "p": {pid: {"x": p.x, "y": p.y, "z": p.z,
                                "hp": p.hp, "shield": p.shield,
                                "kills": p.kills, "state": p.state}
                          for pid, p in self.p.items()},
                    "str": self.structs,
                    "bullets": self.bullets}
            self.broadcast(snap)

# ---------- aiohttp : pages + websockets ----------
game = GameSrv()

async def websocket_upgrade(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    await game.ws_handler(ws, None)
    return ws

async def index(request):
    return web.FileResponse(STATIC_DIR / "index.html")

def create_app():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_static("/static", STATIC_DIR, name="static")
    app.router.add_get("/ws", websocket_upgrade)

    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*")})
    for route in list(app.router.routes()):
        cors.add(route)
    app.on_startup.append(lambda app: asyncio.create_task(game.ticker()))
    return app

# ---------- run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))   # 10000 local, PORT fourni par Render
    print(f"Starting server on 0.0.0.0:{port}")
    web.run_app(create_app(), host="0.0.0.0", port=port)