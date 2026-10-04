# Local Mac handoff: actual Doom and the Chromatic

Paste the following into a **local Codex chat on the Mac connected to your
Chromatic**. Repository work, desktop tests and hardware discovery can proceed
first. The firmware decision comes after the candidate and backup are ready
for review.

```text
Continue the actual Doom implementation in IonutGStan06/chromatic_lab.

Clone or update https://github.com/IonutGStan06/chromatic_lab while preserving
existing local work. Read doom/README.md, doom/engine/README.md and
doom/receiver/README.md. Use the installed Chromatic plugin and its
modretro-chromatic:chromatic-deployment skill for physical device work.

The repository contains the real Doom engine and the original nine-level
shareware IWAD. Doom runs on this Mac. The experimental handheld path sends
rendered frames to a CGB receiver and returns the Chromatic's buttons. Sound
is currently disabled. The receiver ROM alone does not run Doom.

First complete the local preview:
- Prepare Python 3.12, a C compiler/Make and requirements-dev.txt.
- Build the engine with make -C doom/engine.
- Run python doom/play.py, then check --level 1 through --level 9,
  --scale 3 and --original as appropriate.
- Install/configure GBDK 4.5.0, then run make doom and make doom-test.
- Verify turning, movement, firing, doors, menu and exit behavior using
  normal inputs. Keep source licenses and the original shareware checksum.

Then discover the connected Chromatic with the deployment skill. Report
whether the Mac can actually access it and identify its current firmware.
The cloud could not access this hardware, so physical validation is pending.

The handheld route requires the experimental ChromatiX-vcart FPGA design:
https://github.com/enjoy-digital/chromatix/tree/0adf3822613a0230d18e0d73193f78337d1100b6
Use the csr.csv matching that exact firmware/build. This SRAM/debug protocol
is different from the plugin's ordinary live-demo ROM transfer.

Before any firmware write, prepare and verify a backup of the current image,
identify the exact candidate and its checksum, explain the change and the
tested/documented restoration procedure, and obtain my explicit local
confirmation. Desktop testing and device inspection are authorized now.
No cartridge erase or cartridge flashing is part of this task.

Once the approved matching firmware is available, identify its actual debug
serial port and start litex_server manually, bound to 127.0.0.1 on port 1234.
Run:
python doom/play.py --connect --csr-csv /absolute/path/to/matching/csr.csv
The optional endpoint arguments are --host 127.0.0.1 --port 1234.

Test the complete physical path: receiver loading, first-frame acknowledgement,
continued video, D-pad motion/turning, A fire, B use/open, Start confirm and
Select menu. Capture a real hardware frame/video with the plugin if supported.
Measure responsiveness and observed frame rate; distinguish these from the
cloud emulator checks. Preserve the firmware backup and record the versions
and commands that actually worked. Continue supported troubleshooting and
report concrete remaining blockers without claiming unperformed tests.
```

For reference, the serial bridge command after the debug port is verified is:

```sh
litex_server --uart --uart-port /dev/cu.YOUR_CHROMATIC_DEBUG_PORT \
  --bind-ip 127.0.0.1 --bind-port 1234
```

The transport and ROM operate on a virtual cartridge in RAM. Installing
ChromatiX changes the FPGA firmware stored on the handheld; it is therefore
reviewed and confirmed separately. This handoff intentionally includes no
unconditional firmware-flash command.
