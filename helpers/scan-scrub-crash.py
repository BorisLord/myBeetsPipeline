#!/usr/bin/env python3
# Count files that would crash scrub: embedded image with mime_type=None (confirmed for ASF/WMA).
# Read-only (modifies nothing). Scans ALL formats to be thorough.
import subprocess, mediafile, collections, os
root = os.environ.get('ROOT', os.environ.get('MUSIC_SRC', os.path.expanduser('~/Music/beetsPipeline/source')))
exts = ['*.' + e for e in os.environ.get('EXTS', 'wma mp3 flac m4a ogg opus aac wav').split()]
cmd = ['find', root, '-type', 'f', '(']
for i, e in enumerate(exts):
    if i: cmd += ['-o']
    cmd += ['-iname', e]
cmd += [')']
files = subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()
bad = []; err = 0; by_ext = collections.Counter()
for f in files:
    try:
        mf = mediafile.MediaFile(f)
        if any(getattr(img, 'mime_type', None) is None for img in (mf.images or [])):
            bad.append(f); by_ext[f.rsplit('.', 1)[-1].lower()] += 1
    except Exception:
        err += 1
print(f"files scanned: {len(files)}")
print(f"scrub CRASHERS (image mime=None): {len(bad)}")
print(f"by extension: {dict(by_ext)}")
print(f"unreadable (other issue): {err}")
for b in bad[:15]:
    print("  BAD:", b)
