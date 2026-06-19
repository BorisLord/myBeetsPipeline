#!/usr/bin/env python3
# Strip the BROKEN embedded image (mime=None) from files that would crash scrub.
# mf.images=[] = empty list -> nothing to serialize -> no crash. Art comes back via fetchart (02-enrich).
# Optional arg = limit (to test on N files). No arg = all.
import subprocess, mediafile, sys, os
root = os.environ.get('ROOT', os.environ.get('MUSIC_SRC', os.path.expanduser('~/Music/beetsPipeline/source')))
limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10**9
exts = ['*.wma', '*.mp3', '*.flac', '*.m4a', '*.ogg', '*.opus', '*.aac', '*.wav']
cmd = ['find', root, '-type', 'f', '(']
for i, e in enumerate(exts):
    if i: cmd += ['-o']
    cmd += ['-iname', e]
cmd += [')']
files = subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()
fixed = []; failed = []
for f in files:
    if len(fixed) >= limit: break
    try:
        mf = mediafile.MediaFile(f)
        imgs = mf.images
        if imgs and any(getattr(i, 'mime_type', None) is None for i in imgs):
            n = len(imgs)
            mf.images = []
            mf.save()
            after = len(mediafile.MediaFile(f).images or [])
            fixed.append(f); print(f"FIX ({n}->{after} img): {f}")
    except TypeError:
        pass  # mf.images=None -> no image -> skip
    except Exception as e:
        failed.append(f); print(f"FAIL {type(e).__name__}: {f}")
print(f"=== stripped: {len(fixed)} | failed: {len(failed)} ===")
