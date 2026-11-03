"""Deterministic, sample-free entry whoosh. Requires NumPy; uses no external audio."""
from pathlib import Path
import hashlib
import json
import wave
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RATE = 48000
DURATION = 0.62
PEAK_TIME = 0.405
SEED = 731915


def air_sweep(rng, length):
    """Overlap-add a broad moving spectral band: a rush, rather than a tonal whistle."""
    frame, hop = 1024, 128
    raw = rng.standard_normal(length + frame * 2)
    result = np.zeros_like(raw)
    weight = np.zeros_like(raw)
    window = np.hanning(frame)
    frequencies = np.fft.rfftfreq(frame, 1 / RATE)
    for start in range(0, len(raw) - frame, hop):
        time = (start + frame / 2 - frame) / RATE
        progress = np.clip(time / PEAK_TIME, 0, 1)
        tail = np.clip((time - PEAK_TIME) / (DURATION - PEAK_TIME), 0, 1)
        center = (460 + 4300 * progress ** 1.8) * (1 - 0.72 * tail)
        band = np.exp(-0.5 * (np.log((frequencies + 80) / center) / 0.78) ** 2)
        band *= 1 - np.exp(-(frequencies / 180) ** 4)
        band *= np.exp(-(frequencies / 11000) ** 6)
        spectrum = np.fft.rfft(raw[start:start + frame] * window)
        result[start:start + frame] += np.fft.irfft(spectrum * band) * window
        weight[start:start + frame] += window ** 2
    return (result / np.maximum(weight, 1e-6))[frame:frame + length]


def main():
    rng = np.random.default_rng(SEED)
    length = round(RATE * DURATION)
    time = np.arange(length) / RATE
    air = air_sweep(rng, length)
    side = air_sweep(rng, length)
    attack = np.sin(np.clip(time / PEAK_TIME, 0, 1) * np.pi / 2) ** 2.6
    tail = np.exp(-np.maximum(time - PEAK_TIME, 0) / 0.052)
    envelope = attack * tail
    envelope *= np.sin(np.clip((DURATION - time) / 0.024, 0, 1) * np.pi / 2) ** 2
    # A faint low body adds forward motion without an impact or an explosion.
    frequency = 155 - 85 * np.clip(time / DURATION, 0, 1)
    phase = np.cumsum(frequency) * (2 * np.pi / RATE)
    body = np.sin(phase) * 0.055 * envelope
    center = air * envelope + body
    width = side * envelope * 0.12
    stereo = np.column_stack((center + width, center - width))
    stereo -= stereo.mean(axis=0)
    fade = np.sin(np.clip(time / 0.008, 0, 1) * np.pi / 2) ** 2
    fade *= np.sin(np.clip((DURATION - time) / 0.012, 0, 1) * np.pi / 2) ** 2
    stereo *= fade[:, None]
    stereo *= 0.78 / np.max(np.abs(stereo))
    pcm = np.round(stereo * 32767).astype('<i2')
    pcm[0] = pcm[-1] = 0
    target = ROOT / 'assets/audio/menu_entry_whoosh.wav'
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), 'wb') as sound:
        sound.setparams((2, 2, RATE, length, 'NONE', 'not compressed'))
        sound.writeframes(pcm.tobytes())
    with wave.open(str(target), 'rb') as sound:
        assert sound.getnchannels() == 2 and sound.getframerate() == RATE
        decoded = np.frombuffer(sound.readframes(sound.getnframes()), dtype='<i2').reshape(-1, 2)
    assert np.array_equal(decoded, pcm)
    assert np.max(np.abs(decoded.astype(float))) < 32767
    assert np.all(decoded[0] == 0) and np.all(decoded[-1] == 0)
    report = {
        'file': target.relative_to(ROOT).as_posix(), 'duration': DURATION,
        'sample_rate': RATE, 'channels': 2, 'bits': 16, 'seed': SEED,
        'peak_dbfs': float(20 * np.log10(np.max(np.abs(stereo)))),
        'rms_dbfs': float(20 * np.log10(np.sqrt(np.mean(stereo ** 2)))),
        'clipped_samples': int(np.count_nonzero(np.abs(decoded.astype(float)) >= 32767)),
        'peak_envelope_seconds': PEAK_TIME,
        'trigger': 'EntryShot.hide (0.18s after clicking Start); strongest rush meets black-fade onset.',
        'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'synthesis': 'Seeded filtered noise, moving spectral band, short envelope, subtle low body. No external samples.',
        'checks': 'PCM round trip, header, sample count, zero endpoints, clipping checked. Listening approval remains with user.',
    }
    output = ROOT / 'validation/menu-entry-shot-20261015/whoosh-checks.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
