# NeuralFlow Preview 0.6.0-preview.6

Floating controls remain visible when the main window is minimized. Minimizing
opens them automatically; closing the main app still exits and restores the
original picture. Both windows support resizing, and the floating panel scrolls
when space is limited.

The redesigned panel has synchronized ON/OFF, hold-to-compare, neural strength,
and a More section for stability, clarity, vibrance, contrast, brightness, warmth
and tone. Open full settings restores the main window.

A NeuralFlow icon in the Windows notification area provides a left-click effects
toggle and a right-click menu for ON/OFF, Restore original, Floating controls,
Open NeuralFlow and Exit. Choose a target in Live before enabling effects.
Windows may initially put the icon in its hidden-icons menu.

Validation: compiled app; actual minimize/restore and resizing checks at 540×420
main and 320×360 floating; floating-control binding test; tray initialization;
packaged file hashes and installer payload. Neural pipeline is unchanged.
