"""Reproducible local birdlike synthesis; no recordings or remote generation credits."""
from pathlib import Path
import base64
import hashlib
import json
import uuid
import wave
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets/audio/bird_hints'
RATE = 48000


def syllable(seconds, frequencies, seed, softness=1):
    rng = np.random.default_rng(seed)
    n = round(seconds * RATE)
    t = np.arange(n) / RATE
    u = t / seconds
    anchors = np.linspace(0, 1, len(frequencies))
    pitch = np.interp(u, anchors, frequencies)
    # Tiny independent instabilities keep the notes from sounding like UI beeps.
    pitch += np.interp(u, np.linspace(0, 1, 11), rng.normal(0, 12, 11))
    pitch += 38 * np.sin(2 * np.pi * (28 * t + 9 * t*t)) * np.sin(np.pi*u)
    phase = 2 * np.pi * np.cumsum(pitch) / RATE
    tone = np.sin(phase) + .075*np.sin(2*phase+.3) + .018*np.sin(3*phase)
    air = rng.normal(0, 1, n)
    spectrum = np.fft.rfft(air)
    bins = np.fft.rfftfreq(n, 1/RATE)
    spectrum *= np.exp(-((bins-4200)/1800)**4)
    air = np.fft.irfft(spectrum, n)
    air /= max(1e-8, float(np.std(air)))
    envelope = np.minimum(1, t/.007)**1.3 * np.minimum(1, (seconds-t)/.018)**1.7
    envelope *= np.sin(np.pi * np.minimum(.999999, u))**.35
    envelope *= .78 + .22*np.sin(2*np.pi*19*t + .8)
    return envelope * (tone + .014/softness*air)


DEFINITIONS = [
    ('bird_hint_soft_pair', '轻啾短句', 2.1, [
        (.12,.135,[3400,4200,3100],.84),
        (.64,.105,[3550,4550,3300],.72),
        (.82,.09,[3700,4300,3100],.59)], 1),
    ('bird_hint_low_chirp', '低柔啾鸣', 2.3, [
        (.16,.23,[2050,2600,2350,1700],.90),
        (1.03,.155,[2200,2750,1800],.57)], 1.3),
    ('bird_hint_tiny_trill', '细碎颤鸣', 2.4, [
        (.14,.082,[3500,4700,3500],.65),
        (.265,.069,[3900,5000,3700],.75),
        (.372,.094,[3700,4550,3050],.82),
        (.515,.08,[3300,4250,3000],.65),
        (.68,.135,[3200,4100,2500],.48)], 1.1),
    ('bird_hint_distant_answer', '远处轻应', 3.1, [
        (.18,.13,[3000,4050,2950],.72),
        (.39,.092,[3300,4200,2900],.61),
        (1.55,.17,[2850,3650,2500],.50)], 1.5),
]


def generate():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for number, (name, label, seconds, notes, softness) in enumerate(DEFINITIONS):
        signal = np.zeros(round(seconds*RATE), dtype=np.float64)
        for index, (start, duration, pitch, gain) in enumerate(notes):
            note = syllable(duration, pitch, 20261020+number*100+index, softness) * gain
            begin = round(start*RATE)
            signal[begin:begin+len(note)] += note
        # One very quiet early reflection, not a continuous outdoor sound bed.
        delay = round(.013*RATE)
        signal[delay:] += signal[:-delay].copy()*.035
        if number == 3:
            freqs = np.fft.rfftfreq(len(signal), 1/RATE)
            signal = np.fft.irfft(np.fft.rfft(signal)/(1+(freqs/4600)**6), len(signal))
        signal -= np.mean(signal)
        signal *= .60 / max(1e-8, float(np.max(np.abs(signal))))
        ramp = round(.025*RATE)
        signal[:ramp] *= np.linspace(0, 1, ramp)
        signal[-ramp:] *= np.linspace(1, 0, ramp)
        path = OUT / (name+'.wav')
        with wave.open(str(path), 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(RATE)
            stream.writeframes(np.rint(signal*32767).astype('<i2').tobytes())
        meta = Path(str(path)+'.meta')
        if not meta.exists():
            meta.write_text(json.dumps({'uuid':base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().rstrip('=')},indent=2)+'\n',encoding='utf-8')
        rows.append({'label':label,'path':str(path.relative_to(ROOT)).replace('\\','/'),
                     'seconds':seconds,'rate':RATE,'channels':1,
                     'peak_dbfs':round(20*np.log10(max(np.abs(signal))),2),
                     'rms_dbfs':round(20*np.log10(np.sqrt(np.mean(signal**2))),2),
                     'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    report = ROOT / 'validation/bird-hints-20261020'
    report.mkdir(parents=True, exist_ok=True)
    (report/'assets.json').write_text(json.dumps({'method':'local procedural synthesis',
        'remote_attempt':'batch_sound_effects: INSUFFICIENT_BALANCE; no audio result returned; not retried',
        'native_listening_verified':False,'clips':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(rows,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    generate()
