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

## Deferred work

The original measurement formulas, filtering, and defaults are preserved.
The [proposed volume correction](https://github.com/jgagneastro/coffeegrindsize/pull/11)
is deliberately not applied. Numerical parity does not independently validate
the scientific model.

Detection remains synchronous; noisy/high-resolution photographs can be slow.
[Cancellation and optimization](https://github.com/jgagneastro/coffeegrindsize/issues/17),
new installers, signing/notarization, and Windows/Linux certification are future
milestones.
