# Models

| Role | Model | Spec | Notes |
| --- | --- | --- | --- |
| Twins (Flash tier) | Gemini Flash | `gemini:gemini-3.5-flash` | thinking level "low" |
| Twins (Pro tier) | Gemini Pro | `gemini:gemini-3.1-pro-preview` | no free-tier quota: needs billing |
| Twins (open model) | Gemma 4 26B-A4B | `gemma:gemma-4-26b-a4b-it` | JSON mode + guided choices (below) |
| Development twins | ILMU mini | `ilmu:ilmu-mini-v3.3` | OpenAI-compatible |
| Onboarding follow-ups, highlights | Gemini Flash | `FOLLOWUP_MODEL`, `HIGHLIGHT_MODEL` override | |
| Twin extraction | Gemini Pro | `EXTRACTION_MODEL` overrides | structured output with a JSON schema |

## Gemma 4: where it's served, and why (F3)

**Decision: Gemma 4 through the Gemini API**, not vLLM on a Cloud Run GPU service.

- The Gemini API serves Gemma 4 (`gemma-4-26b-a4b-it` and `gemma-4-31b-it`) on the same key and client as Gemini, with a free tier, so there is no GPU service to deploy, scale to zero or pay for while idle.
- Guided decoding is available there too: Gemma accepts JSON-mode requests with a response schema. Ladder-rung choices are requested as `{"choice": <enum of the option letters>}`, so a reply can only be a valid option (`GemmaModel.choose_letter`; anything else is retried, never returned).
- Gemma 4 always "thinks" before free text on the Gemini API (20–40 s a call; thinking level and budget are rejected), but answers JSON-mode requests directly in 1–2 s. So speech and reflections are requested as `{"text": ...}` too.
- **26B-A4B over 31B:** the mixture-of-experts model (4B active parameters) answers a constrained choice in ~1 s; the 31B dense model took ~35 s for the same request (measured 2026-10-11).

vLLM on Cloud Run GPUs remains the fallback if the Gemini API stops serving Gemma or its quota is too small for a demo; `GemmaModel` would then become an OpenAI-compatible client with vLLM's `guided_choice`.
