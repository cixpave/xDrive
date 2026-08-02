xDrive for Windows 11 — portable edition
========================================

1. Extract the entire xDrive folder onto the hard drive you want to use.
2. Double-click xDrive.exe.
3. Follow the setup screen to download the portable AI runtime and a model.
4. Open xDrive.exe from that drive whenever you want to use it.

Keep the folder together
------------------------

xDrive.exe is the launcher, while the adjacent _internal folder contains its
private Python runtime and interface files. This layout avoids extracting
runtime files into the Windows temporary folder. You can move the complete
xDrive folder to a different drive letter at any time.

All application-controlled writable state stays inside the xDrive folder:

- data\ — conversations, agent workspace, and the private Edge profile/cache
- models\ — Ollama model weights
- library\ — offline Wikipedia and documentation archives
- tools\ — the portable Ollama and Kiwix programs
- .xdrive-runtime\ — temporary downloads and portable process state
- config.json — settings and first-run completion state

Windows itself may still maintain normal operating-system records such as
security logs or application-launch history. xDrive does not intentionally
store application data in your Windows user profile.

Moving or backing up
--------------------

Close xDrive first, then move or copy the complete folder. Paths are resolved
from xDrive.exe each time it starts, so changing the drive letter needs no
repair step.

Resetting setup
---------------

Use CONFIG > FACTORY RESET in xDrive. Models and offline books are preserved.
The setup page appears the next time the portable app starts.
