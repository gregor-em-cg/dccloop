# PNG reproduction clarification v1.1

The v1 frozen test demanded identical whole PNG bytes. The first actual extracted-package run failed that criterion, and that failure and original oracle remain unchanged. Inspection found identical decompressed scanline data but different embedded `File`, `Date` and render-timing text metadata in all three views. [obs]

For the current contract, render reproduction means identical decoded image samples, dimensions, encoding and color-interpretation chunks; incidental text metadata may differ. Archive/candidate SHA-256 identity remains byte-exact. This is a genuine specification revision, not a retroactive pass under v1. The decoder checks PNG CRCs and rejects unsupported encodings. A deliberately changed pixel must make comparison fail. No render or original scene was altered to obtain the result. [repo tests/check_png_pixels.py:1]
