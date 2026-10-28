# Recommended Unsloth Studio Settings

Release 18 measures models on the computer that will actually run the game. Because
GPU, RAM, quantization, and currently loaded model metadata vary, the in-application
three-sample report is the authority for a final recommendation.

## Initial baseline

For the currently proposed Gemma 4 E4B uncensored model:

- Start Unsloth Studio on a fixed localhost port (for example `unsloth studio -p 8888`),
  create an API key under **Settings → API**, and enter both in D&D Simulator's Local AI
  Setup.
- Load the model explicitly (D&D Simulator's **Load Selected Model**, Unsloth Studio's
  **Select model** dropdown, or `unsloth run --model <repo>:<variant>`), then choose the
  **Loaded and ready** entry from D&D Simulator Settings.
- Start from the load settings proven on the target machine: `max_seq_length` 32768,
  `cache_type_kv` `q8_0`, `n_parallel` 1, `n_batch` 1024, `n_ubatch` 256, all GPU layers.
  If loading fails, the driver resets, or other applications become unstable, reduce
  `n_batch`/`n_ubatch` first, then context, then choose a smaller quantization.
- A large context can remain configured for experimentation, but the game does not
  send anywhere near that amount in ordinary turns. Prefer 16,384 or 32,768 when the
  larger allocation materially lowers token speed or consumes needed memory.
- Keep application output caps bounded: approximately 220 tokens for evaluation,
  concise dialogue/travel, and the existing path-specific caps for structured turns
  and character prose. Larger context does not require larger responses.
- Use a low temperature for schema repair/evaluation and moderate temperature only for
  the first creative narration attempt. Release 18 already applies these policies.
- Leave Unsloth's server-side tools disabled and keep the default `127.0.0.1` bind.

## Acceptance guidance

A primary gameplay model should produce 3/3 valid probe responses, preferably without
compatibility retries, and should score at least 90/100 on the bounded continuity and
mechanical-authority checks. The report marks a model as recommended only when it also
averages no more than eight seconds on the target computer.

Compare models using the same Unsloth Studio context and quantization configuration.
Token rate is useful only when Unsloth Studio returns prompt/completion usage; otherwise
`POST /v1/chat/count_tokens` can supply prompt size. Context and loaded-memory fields are
reported as unavailable rather than guessed when the local API omits them. Unsloth
Studio's API monitor (`GET /api/inference/monitor`, also shown in its UI) reports
per-request token counts and speed for comparison.
