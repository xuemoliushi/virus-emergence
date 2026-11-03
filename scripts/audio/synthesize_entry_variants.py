"""Three deterministic original transition designs, synthesized with NumPy only."""
from pathlib import Path
import json
import wave
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'assets/audio/entry_candidates'
REPORT=ROOT/'validation/menu-entry-audio-20261018'
SR=48000
T=1.60
N=round(T*SR)
t=np.arange(N)/SR

def smooth(x):
    x=np.clip(x,0,1)
    return x*x*(3-2*x)

def noise(rng,low,high):
    x=rng.standard_normal(N)
    f=np.fft.rfftfreq(N,1/SR)
    shape=(1-np.exp(-(f/low)**4))*np.exp(-(f/high)**4)
    x=np.fft.irfft(np.fft.rfft(x)*shape,n=N)
    return x/(np.std(x)+1e-9)

def tone(freq):
    return np.sin(2*np.pi*np.cumsum(np.broadcast_to(freq,(N,)))/SR)

def envelope(peak=.43,decay=.25):
    return smooth(t/peak)**1.5*np.exp(-np.maximum(t-peak,0)/decay)

def space(mid,side,wet):
    # Dry bass stays centred. Decaying, diffuse reflections widen the upper texture.
    lr=np.column_stack((mid+side,mid-side))
    for i,delay in enumerate([.027,.047,.079,.113,.163,.229,.307,.409]):
        k=round(delay*SR)
        source=np.column_stack((mid-side,mid+side)) if i%2 else np.column_stack((side+mid,mid-side))
        lr[k:]+=source[:-k]*wet*np.exp(-delay/.20)*(-1 if i%3==0 else 1)
    return lr

def design(kind):
    rng=np.random.default_rng(731918+kind)
    env=envelope()
    if kind==1:
        # Deep pressure swell: no bright cartoon whistle, impact or sharp onset.
        body=tone(83-37*smooth(t/.75))*.24
        breath=noise(rng,100,1150)*.24+noise(rng,500,2500)*.055
        mid=(body+breath)*env
        side=noise(rng,650,3300)*envelope(.48,.34)*.055
        return space(mid,side,.26)
    if kind==2:
        # Viscous membrane stretch, followed by a restrained resonant release.
        freq=145-75*smooth(t/.9)+8*np.sin(t*9)*np.exp(-t*3)
        stretch=tone(freq)*.11+tone(freq*1.47)*.055
        fluid=noise(rng,160,1900)*(.17+.045*np.sin(t*32))
        contact=np.exp(-((t-.45)/.045)**2)
        soft_release=noise(rng,230,3200)*contact*.10
        mid=(stretch+fluid)*envelope(.42,.28)+soft_release
        side=noise(rng,450,2600)*envelope(.46,.36)*.045
        return space(mid,side,.32)
    # Microscale texture: many tiny, soft grains cross a broad low bed.
    mid=(noise(rng,110,1050)*.13+tone(110-57*smooth(t/.9))*.10)*envelope(.46,.32)
    side=np.zeros(N)
    for _ in range(46):
        center=rng.uniform(.16,.82)
        duration=rng.uniform(.010,.035)
        window=np.exp(-((t-center)/duration)**2)
        grain=noise(rng,750,3500)*window*rng.uniform(.015,.055)*np.exp(-abs(center-.46)*5)
        pan=rng.uniform(-1,1)
        mid+=grain;side+=grain*pan*.7
    return space(mid,side,.4)

def main():
    OUT.mkdir(parents=True,exist_ok=True);REPORT.mkdir(parents=True,exist_ok=True)
    report=[]
    for i,name in enumerate(['01_pressure','02_membrane','03_micrograins'],1):
        x=design(i)
        x-=x.mean(axis=0)
        x*= (smooth(t/.015)*smooth((T-t)/.16))[:,None]
        # Match overall energy for a fair comparison; avoid choosing by louder playback.
        x*=10**(-23/20)/np.sqrt(np.mean(x*x))
        peak=np.max(np.abs(x))
        if peak>.70:x*=.70/peak
        pcm=np.round(x*32767).astype('<i2');pcm[0]=pcm[-1]=0
        path=OUT/(name+'.wav')
        with wave.open(str(path),'wb') as w:
            w.setparams((2,2,SR,N,'NONE','not compressed'));w.writeframes(pcm.tobytes())
        assert np.isfinite(x).all() and np.max(np.abs(x))<1
        assert np.all(pcm[0]==0) and np.all(pcm[-1]==0)
        report.append({'name':name,'file':path.relative_to(ROOT).as_posix(),'seconds':T,
            'peak_dbfs':float(20*np.log10(np.max(np.abs(x)))),
            'rms_dbfs':float(20*np.log10(np.sqrt(np.mean(x*x)))),
            'clipped_samples':int(np.count_nonzero(np.abs(pcm.astype(float))>=32767)),
            'sample_rate':SR,'channels':2,'bits':16,'trigger_seconds':.60,
            'scope':'Original Python synthesis, no external samples. Candidate only; runtime selection unchanged.'})
    (REPORT/'audio-checks.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report))

if __name__=='__main__':main()
