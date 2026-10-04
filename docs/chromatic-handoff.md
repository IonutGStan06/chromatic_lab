# Local Mac handoff

Keep cloud development and USB deployment in separate tasks. Pull this repository or unpack the source archive on your Mac, then start a **local Codex task in that checkout** with the ModRetro Chromatic plugin enabled. The cloud task cannot reach Mac USB devices.

The intended artifact is `roms/chromatic-arcade.gbc`. It is our source-built homebrew ROM, 32,768 bytes, color-compatible, ROM-only, with no save RAM. Verify its digest against `roms/SHA256SUMS`. Do not substitute a different cartridge file when deploying.

Suggested local task:

> Use the modretro-chromatic:chromatic-deployment skill for this checkout. Inspect roms/chromatic-arcade.gbc, verify its size and SHA-256, discover my connected Chromatic, and show the selected device. Start a live demo of this exact ROM. Test the five launcher entries and their controls. Do not flash a cartridge as part of this live-demo request.

The deployment skill uses these steps:

1. Prepare only missing plugin dependencies using its supported `toolchain_doctor` / `toolchain_prepare` workflow. A built ROM needs the runtime for device actions; rebuilding this C project also needs GBDK. Do not recreate or reinstall a working plugin to obtain a compiler.
2. Authorize this actual checkout as the plugin's project/workspace, then inspect the intended ROM with `rom_inspect`. This repository is a GBDK C project, so it has no `.gbsproj` to select. Use the plugin's supported workspace access for external ROMs.
3. `device` status describes requirements; `list_devices` performs discovery. Select the intended returned `deviceToken`; do not assume player 1. Discovery tokens expire and are consumed by accepted actions.
4. `play` streams host-emulated video/audio to the Chromatic. That live demo does **not** write the cartridge and does **not** prove native cartridge execution.
5. For real cartridge installation, request a separate flash of the exact inspected file to a supported homebrew cartridge. Before the first flash, explicitly acknowledge that it **erases the selected cartridge's existing game data, saves may be lost, and no backup is made**, then approve that specific write. Rediscover and select the device as required.
6. If the device explicitly requires Developer Mode, use the official [ModRetro Updater](https://support.modretro.com/en_us/articles/chromatic-firmware-updater-ryhoYnzCx). Activation codes belong in that updater, never chat. A generic write failure does not establish an activation problem.
7. Preserve any uncertain write result and inspect its original operation status. Do not automatically retry a timed-out flash. Check the installed game separately from an emulator or live stream.

For physical acceptance, check the launcher, all buttons, pauses, scoring, death/retry, sound effects, and each game's pacing on the device. The cloud report covers emulator execution only. For a Mac physical video capture, the deployment skill requires the user to enable capture and grant normal macOS access; any returned capture page opens in Codex's built-in browser.

No hardware action or cartridge write was performed in the cloud task.
