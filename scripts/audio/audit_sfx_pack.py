import argparse, hashlib, io, json, wave, zipfile
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--source')
parser.add_argument('--output', default='sfx_pack_review')
args = parser.parse_args()
OUT = ROOT / 'validation' / args.output
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = Path(r'C:/Users/admin/Documents/WeChat Files/wxid_u7qymtfxqhw822/FileStorage/File/2026-10/12音效.zip')
if args.source: SOURCE = Path(args.source)
targets = dict(absorb_pulse=.4, virus_absorb=.12, infection_complete=.5, swarm_split=.35,
               swarm_merge=.4, swarm_hit=.25, node_hit=.3, swarm_cleared=.7,
               action_denied=.15, skill_dash=.45, card_acquired=.65, ending_defeat=1.8)
targets.update(release_batch=.5,cell_dead=.6,node_warning=.45,alert_up=.8,skill_recall=.6,
    skill_decoy=.35,tail_preserve=.65,node_cover=.5,shield_block=.35,node_takeover=.6,
    switch_control=.18,anchor_on=.2,anchor_off=.18,hide_enter=.4,hide_exit=.3,
    glide_start=.3,flow_redirect=.8,dispatch_gather=.25,dispatch_hold=.25,
    camouflage_on=.4,micro_ambience=30)
results = []
signals = {}
with zipfile.ZipFile(SOURCE) as z:
    for info in z.infolist():
        if not info.filename.lower().endswith('.wav'): continue
        name = Path(info.filename).name
        if name in signals: raise ValueError('Duplicate WAV basename: '+name)
        blob = z.read(info)
        (OUT / name).write_bytes(blob)
        with wave.open(io.BytesIO(blob)) as w:
            rate, channels, width, frames = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
            raw = w.readframes(frames)
        if width != 2: raise ValueError((name, width))
        x = np.frombuffer(raw, dtype='<i2').astype(float).reshape(-1, channels) / 32768
        mono = x.mean(axis=1); signals[name] = mono
        peak = float(np.max(np.abs(x))); rms = float(np.sqrt(np.mean(x*x)))
        active = np.flatnonzero(np.abs(mono) > 10**(-60/20))
        spec = np.abs(np.fft.rfft(mono*np.hanning(len(mono))))**2
        freq = np.fft.rfftfreq(len(mono), 1/rate)
        bins = spec / max(spec.sum(), 1e-30)
        top = np.argsort(spec)[-8:][::-1]
        chunks = [mono[i:i+240] for i in range(0,len(mono),240)]
        env = [float(np.sqrt(np.mean(c*c))) for c in chunks]
        r = dict(file=name, sha256=hashlib.sha256(blob).hexdigest(), rate=rate, channels=channels, bits=width*8, duration=frames/rate,
            target=targets.get(Path(name).stem), peak_db=20*np.log10(max(peak,1e-15)),
            rms_db=20*np.log10(max(rms,1e-15)), clipped_samples=int(np.sum(np.abs(x)>=32767/32768)),
            dc=float(mono.mean()), leading_ms=float(active[0]/rate*1000) if len(active) else None,
            trailing_ms=float((len(mono)-1-active[-1])/rate*1000) if len(active) else None,
            first_sample=float(mono[0]), last_sample=float(mono[-1]),
            last_10ms_rms_db=20*np.log10(max(float(np.sqrt(np.mean(mono[-480:]**2))),1e-15)),
            centroid_hz=float((bins*freq).sum()),
            energy_below_200=float(bins[freq<200].sum()), energy_above_6000=float(bins[freq>6000].sum()),
            top_frequencies_hz=[round(float(freq[i]),1) for i in top],
            envelope_5ms=env)
        results.append(r)
        if channels == 2:
            delta = np.diff(x, axis=0)
            seam = x[0]-x[-1]
            r['loop_seam_delta'] = seam.tolist()
            r['normal_delta_rms'] = float(np.sqrt(np.mean(delta*delta)))
            r['normal_delta_abs_p99'] = float(np.quantile(np.abs(delta),.99))
            r['stereo_correlation'] = float(np.corrcoef(x.T)[0,1])
            r['mono_rms_db'] = float(20*np.log10(max(np.sqrt(np.mean(mono*mono)),1e-15)))
            r['edge_rms_db'] = [float(20*np.log10(max(np.sqrt(np.mean(a*a)),1e-15))) for a in [x[:4800],x[-4800:]]]
(OUT/'measurements.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
for r in results:
    print(json.dumps({k:v for k,v in r.items() if k!='envelope_5ms'},ensure_ascii=False))
# Compare aligned waveforms, independent of gain, for possible duplicated sounds.
for i,a in enumerate(signals):
    for b in list(signals)[i+1:]:
        n=min(len(signals[a]),len(signals[b])); u,v=signals[a][:n],signals[b][:n]
        corr=float(np.dot(u,v)/max(np.linalg.norm(u)*np.linalg.norm(v),1e-30))
        if abs(corr)>.75: print('SIMILAR',a,b,corr)
