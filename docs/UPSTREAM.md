# Upstream provenance

This MIT-licensed project was created by Jonathan Gagné in 2018.

- Original: https://github.com/jgagneastro/coffeegrindsize
- Original baseline: `22661ebd21831dba4cf32bfc6ba59fe3d49f879c`
- Last application change: `6b6b76ed5b94a6cd2399ab7d3b4b5204f543bbfb` (April 2019)
- Packaging fork: https://github.com/csatt/coffeegrindsize
- Packaging baseline: `29342922a099447e3f00527b899fc8c57ccb1e38`
- Historical release: https://github.com/csatt/coffeegrindsize/releases/tag/v1.0.0

Both baseline application scripts have SHA-256
`7f3445b05a46be7105bafd843e3cc38f52a4c9f9c76d44ed835b92c54eb018ec`.
Chris Satterlee's four commits add installer tooling; the original branch's
additional commit links to those installers. Their common ancestor is
`57f6c48213afda2704478b3fc2d0749332ca9d0e`.

The fork preserves both histories. Bundled applications, generated files, and
large PDF/Pages documents were removed from the development branch. Historical
blobs remain accessible in Git; a partial clone avoids fetching them initially.
Example photographs remain in `Help/`.

## Historical documentation

- [Full manual](https://github.com/jgagneastro/coffeegrindsize/blob/22661ebd21831dba4cf32bfc6ba59fe3d49f879c/Help/coffee_grind_size_manual.pdf)
- [Short manual](https://github.com/jgagneastro/coffeegrindsize/blob/22661ebd21831dba4cf32bfc6ba59fe3d49f879c/Help/coffee_grind_size_summarized_manual.pdf)

`build_tools/` retains Chris's historical PyInstaller/DMG/WiX workflow and
assets for reference. It is not part of the supported development environment.

## Regression evidence and compatibility changes

The unchanged upstream script is stored in `tests/fixtures/legacy_reference.py`.
The baseline includes a synthetic image and 128×128 crops of the better/decent
example photographs at source coordinates `(800, 800, 928, 928)`, in both
detection modes. Pixel memberships are exact; measurements and rounded
statistics match the pinned routines under the current locked dependencies.
Region/filter and all 12 histogram variants are also compared directly against
the pinned routines. This validates extraction and compatibility, not the old
binary installers or the underlying scientific assumptions.

The numerical formulas, including the original volume expression and automatic
log-bin-count expression, are unchanged. Compatibility changes are restricted
to execution and invalid/degenerate input handling:

- Pillow resampling uses `Resampling.LANCZOS`; Matplotlib renders through an
  explicit Agg canvas and actual RGBA buffer dimensions. Tk variable callbacks
  use `trace_add` for compatibility with current Tk.
- Grayscale/palette images are normalized to RGB; alpha is composited on white.
  Unsupported high-bit-depth modes receive a clear error rather than an index
  failure. Valid legacy RGB photographs follow the same analysis path.
- Canceled dialogs preserve state. Invalid/nonpositive calibration and malformed
  CSVs report errors. Empty detections clear statistics and refuse histogram/CSV
  export instead of crashing or exporting misleading data.
- Constant particle sizes get a small finite histogram range and zero CDF
  spread where the old routine was undefined. Nonconstant, one-bin CDF sides
  retain the old interpolated endpoint. Automatic bin counts have a minimum
  of two edges. A manual range containing no particles receives an error.
- Weighted standard deviation no longer mutates the caller's array. The original
  statistics reconstructed weights between calculations; valid outputs match.
- Downsampling invalidates prior results. Simple mode requires recalibration;
  expert mode divides a retained pixels/mm scale by two. The old expert scale
  silently remained incorrect after halving the image.
- Zoom callbacks accept button invocations without an event object. Cluster
  editing and switching back from a histogram restore image-view state.

CPython 3.14.8, Tk 9.1, NumPy 2.5.3, pandas 3.0.6, Pillow 12.3.0, and
Matplotlib 3.11.2 were used for local verification on Apple Silicon macOS 26.5.1.

## Deferred work

The original measurement formulas, filtering, and defaults are preserved.
The [proposed volume correction](https://github.com/jgagneastro/coffeegrindsize/pull/11)
is deliberately not applied. Numerical parity does not independently validate
the scientific model.

Detection remains synchronous; noisy/high-resolution photographs can be slow.
[Cancellation and optimization](https://github.com/jgagneastro/coffeegrindsize/issues/17),
new installers, signing/notarization, and Windows/Linux certification are future
milestones.
