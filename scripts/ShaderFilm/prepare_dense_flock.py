"""Bake a seeded 3D flock for the film's absolute-time WebGL renderer.

Local topological neighbours steer each bird. No frame depends on preview order.
Only the hero leaves the flock at 15 s; the other identities remain continuous.
"""
from pathlib import Path
import json, hashlib
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'assets/video/emergence_shader/flock_v2'
OUT.mkdir(exist_ok=True)
FPS, SECONDS, SEED = 24, 22, 1987
NEAR, FAR = 840, 360
N = NEAR + FAR + 1
rng = np.random.default_rng(SEED)
groups = np.r_[np.zeros(NEAR), np.ones(FAR), 0].astype(int)
hero = N - 1

def limit(v, maximum):
    return v * np.minimum(1, maximum / np.maximum(np.linalg.norm(v, axis=1), .001))[:, None]

def centres(t):
    return np.array([[55*t-80+65*np.sin(t*.32), 30+45*np.sin(t*.44), 1850+75*np.sin(t*.29)],
                     [55*t+80+95*np.sin(t*.23+1), 330+60*np.sin(t*.36+1.1), 2950+140*np.sin(t*.24)]], dtype='float32')

# A curved, thick, irregular volume rather than two thin horizontal strips.
p = np.empty((N, 3), dtype='float32')
for group, count in [(0, NEAR), (1, FAR)]:
    ids = np.flatnonzero(groups == group)
    q = rng.normal(0, 1, (len(ids), 3)).astype('float32')
    q = np.clip(q, -2.15, 2.15)
    q *= [360 if group == 0 else 550, 125 if group == 0 else 145, 230 if group == 0 else 370]
    q[:, 1] += 72*np.sin(q[:, 0]*.0045 + group*1.5)
    q[:, 2] += 115*np.sin(q[:, 0]*.003 + .8)
    p[ids] = q + centres(0)[group]
p[hero] = centres(0)[0] + [80, -190, -170]
v = np.tile(np.array([65., 0., -10.], dtype='float32'), (N, 1))
v += rng.normal(0, [10, 9, 8], v.shape).astype('float32')
bank = np.zeros(N, dtype='float32')
phase = rng.uniform(0, 2*np.pi, N)
frequency = rng.uniform(2.35, 3.65, N)
size = rng.uniform(.72, 1.28, N)
tone = rng.uniform(.12, .39, N)
size[hero], tone[hero] = 1.28, .15
frames = []
dt = 1/48
accel = np.zeros_like(v)
max_accel, max_speed = 0., 0.
for step in range(SECONDS*48+1):
    t = step*dt
    if step % 2 == 0:
        frames.append(np.column_stack((p, v, bank)).astype('<f4'))
    if step == SECONDS*48:
        break
    if step % 4 == 0:
        delta = p[None, :, :] - p[:, None, :]
        d2 = np.einsum('ijk,ijk->ij', delta, delta)
        same = groups[:, None] == groups[None, :]
        np.fill_diagonal(d2, np.inf)
        if t >= 15:
            same[:, hero] = False
            same[hero, :] = False
        # Up to twelve neighbours, within a finite sensing radius.
        masked = np.where(same & (d2 < 195**2), d2, np.inf)
        ids = np.argpartition(masked, 11, axis=1)[:, :12]
        ds = np.take_along_axis(masked, ids, axis=1)
        valid = np.isfinite(ds)
        count = np.maximum(valid.sum(1), 1)
        neighbours = p[ids] - p[:, None, :]
        align = (v[ids]*valid[:, :, None]).sum(1)/count[:, None]-v
        cohesion = (neighbours*valid[:, :, None]).sum(1)/count[:, None]
        separation = -(neighbours / np.maximum(ds[:, :, None], 16) * (ds < 24**2)[:, :, None]).sum(1)
        rel = p - centres(t)[groups]
        # A turning wave reaches different neighbourhoods at different times.
        theta = .56*np.sin(t*.56-rel[:, 0]*.0026+rel[:, 2]*.0011+groups*1.7)
        desired = np.column_stack((68*np.cos(theta), 43*np.sin(theta), -32*np.sin(theta*.85+.3)))
        # Gentle circulation gives the volume thickness and changing negative space.
        desired[:, 1] += rel[:, 2]*.035
        desired[:, 2] -= rel[:, 1]*.035
        accel = .80*align + .035*cohesion + 540*separation + .60*(desired-v)
        # A broad soft envelope, not a prescribed location for individual birds.
        radii = np.where(groups[:, None] == 0, [780, 350, 520], [1250, 420, 760])
        excess = np.maximum(np.abs(rel)-radii, 0)*np.sign(rel)
        accel -= excess*.14
        accel = limit(accel.astype('float32'), 55)
        if t >= 15:
            elapsed = t-15
            accel[hero] = [10*np.exp(-elapsed), -28-12*min(elapsed, 3), 0]
        max_accel = max(max_accel, float(np.linalg.norm(accel, axis=1).max()))
    old = v.copy()
    v += accel*dt
    v[:hero] = limit(v[:hero], 96)
    p += v*dt
    # Filtered banking follows actual heading change; no independent random spinning.
    target_bank = np.clip(-accel[:, 2]*.016, -.66, .66)
    bank += (target_bank-bank)*(1-np.exp(-dt*4))
    if t >= 15:
        bank[hero] = .3*np.sin((t-15)*2.1)+min((t-15)*.17, .9)
    max_speed = max(max_speed, float(np.linalg.norm(v[:hero], axis=1).max()))
    if step % 192 == 0:
        print(f'baked {t:.0f}/{SECONDS}s', flush=True)

data = np.stack(frames)
assert np.isfinite(data).all()
binary = data.tobytes()
(OUT/'motion.f32').write_bytes(binary)
meta = dict(version=2, seed=SEED, fps=FPS, seconds=SECONDS, count=N, near_count=NEAR+1,
            far_count=FAR, hero=hero, stride=7, frame_count=len(frames),
            layout=['x','y','z','vx','vy','vz','bank'],
            phase=phase.tolist(), frequency=frequency.tolist(), size=size.tolist(), tone=tone.tolist(),
            group=groups.tolist(), sha256=hashlib.sha256(binary).hexdigest(),
            simulation=dict(neighbour_limit=12, sensing_radius=195, separation_radius=24,
                            fixed_dt=dt, force_hz=12, max_normal_speed=max_speed,
                            max_acceleration_including_fall=max_accel,
                            wrap=False, hero_leaves_neighbourhood_at=15))
(OUT/'manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'{N} birds, {len(frames)} frames, {len(binary)/1024**2:.1f} MiB', flush=True)
