# Third-Party Notices

ClipClean invokes FFmpeg and FFprobe as separate executable programs for
media probing, audio/video matching, and output encoding.

## FFmpeg

The Windows release bundle includes the following FFmpeg build:

- Provider: gyan.dev
- Version: `2026-10-12-git-615b07170e-full_build-www.gyan.dev`
- Source commit: `615b07170e`
- License: GNU General Public License v3 (GPLv3)
- Source: <https://github.com/FFmpeg/FFmpeg/commit/615b07170e>
- Provider build information: <https://www.gyan.dev/ffmpeg/builds/>

The exact GPLv3 license text is included at
`licenses/ffmpeg-gpl-3.0.txt`.

FFmpeg is a separate third-party program. It is not part of the ClipClean
source code. The FFmpeg copyright and license belong to the FFmpeg project,
its contributors, and the respective component authors.

The bundled FFmpeg was built with GPL-enabled components, including
`libx264` and `libx265`. Anyone redistributing the Windows bundle should
preserve this notice and the accompanying license text, and should comply
with the applicable GPLv3 source-correspondence requirements for the exact
FFmpeg build.

## User media

ClipClean does not include the project's development videos, advertisement
references, logs, reports, or generated output files. Users are responsible
for having the necessary rights to process and redistribute their own media.
