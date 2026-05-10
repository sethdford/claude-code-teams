---
name: verify-ui
description: Verify UI changes by capturing before/after screenshots and asking Claude vision to judge whether the change matches intent and didn't break anything else. Mano-verify pattern (arXiv 2509.17336 — #1 on OSWorld at 58.2%). Use after any frontend change. Triggers on /verify-ui, "verify the UI", "check the screenshot", "did the visual change work".
when_to_use: After any change to frontend code (HTML/CSS/React/Vue/etc) where the visible behavior matters. Cheaper and broader than running E2E browser tests. NOT for pure logic changes (use /verify or /exec-grounded).
allowed-tools: mcp__Claude_Preview__preview_start, mcp__Claude_Preview__preview_screenshot, mcp__Claude_Preview__preview_eval, mcp__Claude_Preview__preview_inspect, mcp__Claude_in_Chrome__tabs_create_mcp, mcp__Claude_in_Chrome__navigate, mcp__Claude_in_Chrome__computer, Read, Bash
arguments: [intent]
---

# /verify-ui — Multi-modal UI verification

`/verify-ui "<intent>"` captures before/after screenshots and asks Claude vision to judge whether the visible change matches the stated intent — and whether anything else changed unexpectedly.

Pattern from **Mano-verify** ([arXiv 2509.17336](https://arxiv.org/html/2509.17336), Sep 2025) — the verifier reasons over (pre-image, post-image, intent text) jointly, not just text. #1 on OSWorld specialized at 58.2%.

## When to use

- Pixel-shifted layouts (margins, alignment)
- Color or typography drift
- Component visibility (something appeared/disappeared)
- Unintentional regressions (you fixed component A, but B looks broken now)
- Accessibility-relevant visual changes (focus rings, contrast)

## When NOT to use

- Pure logic changes (use `/verify` with the verifier agent — runs tests, no UI)
- Backend API changes
- When the dev server isn't running and you can't start it

## Protocol you must follow

### 1. Confirm intent
- The user told you what they wanted ("change the button color to blue", "add a loading spinner", …). Restate it back in 1 sentence.
- If intent is vague ("make it look better"), STOP — ask for specificity. UI verification needs a concrete claim.

### 2. Capture BEFORE state
- Find the dev server config: `.claude/launch.json` or ask the user
- `preview_start` if not running
- `preview_screenshot` — save the result. This is the BASELINE.

### 3. Apply the change
- Edit/Write the actual code
- Reload the preview (`preview_eval` with `location.reload()` or wait for HMR)
- For visible-immediately changes, capture stops here

### 4. Capture AFTER state
- `preview_screenshot` again. This is the POST-CHANGE state.

### 5. Vision judge
You have BEFORE and AFTER images in context plus the intent text. Reason explicitly:

- **Did the intended change occur?** (Compare before and after for the specific feature mentioned in intent.)
- **Did anything else change?** (Scan the rest of the screenshot for layout shifts, color drift, missing elements, broken icons.)
- **Is there an obvious regression?** (Cut-off text, overlapping elements, broken hover states, wrong-direction shifts.)

Don't pixel-diff — diff *meaningfully*. Anti-aliasing, font hinting, browser version drift produce pixel changes that aren't real regressions.

### 6. Report

```
INTENT: <one sentence>
BEFORE: <path to screenshot 1>
AFTER:  <path to screenshot 2>

VERDICT: pass | fail | escalate
CONFIDENCE: 0.0 - 1.0
INTENDED_CHANGE: <observed | not observed | partial>
UNEXPECTED_CHANGES: <none | list with descriptions>

Last line: RESULT_verify-ui=PASS|FAIL|ESCALATE
```

ESCALATE = "I see changes I can't classify as expected or regression — surface to lead."

## Use with /aspect-panel

For high-stakes frontend work (release-blocking, accessibility-critical, brand-affecting), run BOTH:
1. `/verify-ui` — visual judge of the rendered change
2. `/aspect-panel` with accessibility-reviewer agent — code-level a11y check

Together they catch:
- visual drift (panel can't see)
- a11y regressions in code (visual judge can't see semantic structure)

## DOM + screenshot dual-grounding (advanced)

Going beyond pure pixel comparison: `preview_inspect` returns computed styles + bounding box for any selector. Use this when the user's intent is precise:

- Intent: "make the button 8px taller"
- preview_inspect on the button selector — read computed `height` before
- Apply change
- preview_inspect again — confirm height is +8px
- Then screenshot to confirm no other layout shift

This is more reliable than pure vision for measurable changes.

## Anti-patterns

- **Asking the user "does this look right?"** — that's not verification, that's deferral. Capture the screenshots and judge yourself; surface low confidence as ESCALATE.
- **Pixel-diff with no semantic understanding** — vision-LLMs are better than diff tools at ignoring noise (anti-aliasing, sub-pixel rendering). Use them.
- **Skipping the BEFORE capture** — without baseline, you can't claim regression-free. Capture even if it costs an extra round-trip.
- **Verifying with the dev server in a stale state** — always reload between change and AFTER screenshot.
- **Running on a 1-line CSS color change** — overkill. The dev server preview shows it instantly; you don't need a Mano-verify pass.

## Cost

- 2 screenshots × ~50ms each (cheap)
- 1 vision-LLM call (~$0.01-0.03 per check at Claude pricing)
- Compare to Applitools enterprise (~$1k/mo) or running full Playwright visual regression suite (~minutes per change)
