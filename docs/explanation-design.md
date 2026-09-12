# Exploration explanations and state variants

The page group is presentation only. States retain their original keys; each
transition keeps its own action history. Screen families use the existing screen
fingerprint. Page groups use the URL origin/path and hash-router path, without
query strings. Matching page URLs never merge exploration states.

The inspector distinguishes total arrivals, distinct action sequences, and workers.
Compare shows captured properties plus fingerprint differences. A hash difference
cannot disclose the underlying value or establish a bug. Fixture property labels
come from its recorded visible STATE diagnostic; arbitrary website internals are
not inferred from screenshots.

## Prompt and output framework

`swarmci/narration.py` is a DSPy 3.3.1 program, not an ad-hoc completion prompt:

1. `TransitionEvidence` contains prefix-scoped facts for a single recorded action.
2. `ExplainTransitions` is a typed DSPy signature. `LabeledFewShot.compile` adds
   four reviewed examples: convergence, a distinct variant, handoff, and uncertainty.
3. `JSONAdapter` parses `Explanation` and its cited `GroundedText` fields.
4. Deterministic validation checks edge ordering, fact references and display limits.
5. `ReviewNarration`, a second typed DSPy signature, checks semantic support for
   the headline and sentences. `NarrationProgram` permits one corrected draft.
6. Only accepted results enter the SQLite cache, keyed by run, edge, prompt version
   and evidence fingerprint. Model output never changes state keys or bug status.

Both writing and review use DeepSeek V4.1 Flash through Respan, requested as
`deepseek/deepseek-flash` over DSPy's OpenAI-compatible transport. No local small
model, teacher model or fallback is used. The client requests thinking mode off and low reasoning effort; the gateway may
retain provider reasoning. A bounded token allowance accommodates it. Only the
validated final fields are displayed; semantic review is a separate model call.
Browser workers do not wait for narration. Existing recorded facts remain available
if the gateway or validation fails. The model review reduces unsupported claims;
it is not a mathematical guarantee of truth.

## Reading experience

The main explanation has a short outcome headline, one sentence about the action,
and one about its significance. Each maps to the exact action shown. Evidence opens
the supporting facts in the inspector. Live bursts have a six-second reading window;
playback advances at 6.5 seconds per action at 1x. Pin holds the explanation. Scrubbing
selects the matching action rather than showing a later run summary. Loading and
unavailable states do not substitute fabricated narration. Verification remains in
Findings rather than being retrospectively attributed to every action on that state.

## References

- DSPy typed signatures: https://dspy.ai/learn/programming/signatures/
- DSPy LabeledFewShot: https://dspy.ai/api/optimizers/LabeledFewShot/
- DSPy JSONAdapter: https://dspy.ai/api/adapters/JSONAdapter/
- Respan DSPy gateway: https://respan.ai/docs/integrations/gateway/ds-py
- DeepSeek model alias: https://www.deepseek.com/en/news/deepseek-v4-1-flash/
- DeepSeek thinking controls: https://api-docs.deepseek.com/guides/thinking_mode
- Explanation design: https://www.microsoft.com/en-us/haxtoolkit/guideline/make-clear-why-the-system-did-what-it-did/

Validation covers identity preservation, unique-path counts, no future bug evidence,
unknown citations, grounding-review rejection and cache reuse in tests/test_narration.py.
