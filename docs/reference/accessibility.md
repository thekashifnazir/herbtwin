# Accessibility

Checked on 21 Oct with axe-core (WCAG 2.0 to 2.2, A and AA) on the home, wait, answer
and spot pages, light and dark, at 390 px. One miss: the dark-mode "(optional)" by
"Where is it?" at 3.98:1, now 5.4:1, with a test. Every stop in a keyboard walk of the
home page shows a focus ring; nothing but inline credit and licence links is under
44 px; the pages reflow at 320 px with no sideways scroll; the page motion is off under
Reduce Motion. Not yet done: a test with a real screen reader.

The pass was run against the live site's code on 21 Oct; the one fix is covered by a test
in the repo. Still to do: a pass with a real screen reader (VoiceOver), which would let us
drop the line above.
