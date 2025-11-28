/* eslint-disable no-unused-vars */
/* Mini 1v1 build-fight – client WebGL très simplifié */
const canvas = document.getElementById("c"), ctx = canvas.getContext("2d");
canvas.width = window.innerWidth; canvas.height = window.innerHeight;

const proto = location.protocol === "https:" ? "wss://" : "ws://";
const WS_URL = proto + location.host + "/ws";
const socket = new WebSocket(WS_URL);

let pid = null, players = {}, structs = [], bullets = [];
let cam = {x: 0, y: 2, z: 5, yaw: 0, pitch: -0.2};
let keys = {}, mx = 0, my = 0, building = false;
let sel = 0, selNames = ["wall", "floor", "stair", "cone"];
let mat = "wood", hp = 100, shield = 100, kills = 0, state = "alive";

socket.onmessage = e => {
  const m = JSON.parse(e.data);
  if (m.t === "id") pid = m.pid;
  if (m.t === "snap") {
    players = m.p; structs = m.str; bullets = m.bullets;
    if (players[pid]) { hp = players[pid].hp; shield = players[pid].shield; kills = players[pid].kills; state = players[pid].state; }
    document.getElementById("k").textContent = kills;
    document.getElementById("hp").textContent = hp;
    document.getElementById("sh").textContent = shield;
    document.getElementById("mat").textContent = mat;
    document.getElementById("typ").textContent = selNames[sel];
  }
  if (m.t === "end") alert(m.winner === pid ? "YOU WIN" : "YOU LOSE");
};

window.onkeydown = e => keys[e.key.toLowerCase()] = true;
window.onkeyup = e => keys[e.key.toLowerCase()] = false;
window.onmousemove = e => { mx = e.movementX; my = e.movementY; };
window.onmousedown = e => { if (e.button === 0) shoot(); };
window.onwheel = e => { sel = (sel + Math.sign(e.deltaY) + 4) % 4; mat = selNames[sel]; };

function shoot() {
  const yaw = cam.yaw, pitch = cam.pitch;
  const dx = Math.sin(yaw) * Math.cos(pitch), dy = Math.sin(pitch), dz = Math.cos(yaw) * Math.cos(pitch);
  socket.send(JSON.stringify({ t: "shoot", dx, dy, dz, w: "ar" }));
}
function place() {
  const yaw = cam.yaw, pitch = cam.pitch;
  const dx = Math.sin(yaw) * Math.cos(pitch), dy = Math.sin(pitch), dz = Math.cos(yaw) * Math.cos(pitch);
  let px = cam.x, py = cam.y, pz = cam.z;
  for (let i = 0; i < 50; i++) { px += dx * 0.5; py += dy * 0.5; pz += dz * 0.5; if (py <= 0) { py = 0; break; } }
  socket.send(JSON.stringify({ t: "build", x: px, y: py, z: pz, mat }));
}

let last = performance.now();
function loop(t) {
  const dt = (t - last) / 1000; last = t;
  // camera
  cam.yaw -= mx * 0.003; cam.pitch += my * 0.003;
  cam.pitch = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, cam.pitch));
  mx = my = 0;
  // move
  let fx = 0, fz = 0, speed = 5;
  if (keys["w"]) fz = -1; if (keys["s"]) fz = 1;
  if (keys["a"]) fx = -1; if (keys["d"]) fx = 1;
  const yaw = cam.yaw;
  const dx = fx * Math.cos(yaw) - fz * Math.sin(yaw);
  const dz = fx * Math.sin(yaw) + fz * Math.cos(yaw);
  cam.x += dx * speed * dt; cam.z += dz * speed * dt;
  socket.send(JSON.stringify({ t: "move", x: cam.x, y: cam.y, z: cam.z, yaw: cam.yaw, pitch: cam.pitch }));
  // build
  if (keys["q"]) building = true;
  if (!keys["q"] && building) { building = false; place(); }

  // dessin 2D ultra-simple
  ctx.fillStyle = "#222"; ctx.fillRect(0, 0, canvas.width, canvas.height);
  // sol
  ctx.strokeStyle = "#444"; ctx.beginPath(); ctx.moveTo(0, canvas.height - 50); ctx.lineTo(canvas.width, canvas.height - 50); ctx.stroke();
  // structures
  structs.forEach(s => {
    const sx = (s.x - cam.x) * 50 + canvas.width / 2;
    const sz = (s.z - cam.z) * 50 + canvas.height / 2;
    ctx.fillStyle = { wood: "#b88", stone: "#999", metal: "#ccd" }[s.type];
    ctx.fillRect(sx - 10, sz - 10, 20, 20);
  });
  // players
  for (let id in players) {
    const p = players[id];
    const sx = (p.x - cam.x) * 50 + canvas.width / 2;
    const sz = (p.z - cam.z) * 50 + canvas.height / 2;
    ctx.fillStyle = id == pid ? "#0f0" : "#f00";
    ctx.fillRect(sx - 5, sz - 5, 10, 10);
  }
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);