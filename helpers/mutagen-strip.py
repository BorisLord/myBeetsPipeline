#!/usr/bin/env python3
# Strip embedded images via DIRECT MUTAGEN (more robust than mediafile) on files that
# still have an image with mime=None (= those the first mediafile strip could not save).
import subprocess, mediafile, os
from mutagen.id3 import ID3
from mutagen.asf import ASF
from mutagen.mp4 import MP4
from mutagen.flac import FLAC
root = os.environ.get('ROOT', os.environ.get('MUSIC_SRC', os.path.expanduser('~/Music/beetsPipeline/source')))
exts = ['*.' + e for e in os.environ.get('EXTS', 'wma mp3 flac m4a ogg opus aac wav').split()]
cmd = ['find', root, '-type', 'f', '(']
for i, e in enumerate(exts):
    if i: cmd += ['-o']
    cmd += ['-iname', e]
cmd += [')']
files = subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()
targets = []
for f in files:
    try:
        imgs = mediafile.MediaFile(f).images
        if imgs and any(getattr(i, 'mime_type', None) is None for i in imgs):
            targets.append(f)
    except Exception:
        pass
print(f"remaining targets (image mime=None): {len(targets)}")
fixed = []; ko = []
for f in targets:
    ext = f.rsplit('.', 1)[-1].lower()
    try:
        if ext == 'mp3':
            t = ID3(f); t.delall('APIC'); t.save()
        elif ext == 'wma':
            a = ASF(f)
            for k in [k for k in a.keys() if 'Picture' in k]:
                del a[k]
            a.save()
        elif ext in ('m4a', 'aac'):
            m = MP4(f)
            if 'covr' in m: del m['covr']
            m.save()
        elif ext == 'flac':
            c = FLAC(f); c.clear_pictures(); c.save()
        else:
            ko.append((f, 'ext?')); continue
        fixed.append(f)
    except Exception as e:
        ko.append((f, type(e).__name__))
print(f"mutagen-fixes: {len(fixed)} | still failing: {len(ko)}")
for f, e in ko:
    print("KO", e, "::", f)
