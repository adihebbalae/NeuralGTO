# NeuralGTO — API Contract

> **Source of truth:** `backend/app/models/schemas.py` (Pydantic)
> **Frontend mirror:** `frontend/src/types/api.ts` (TypeScript + Zod)
>
> Last updated: 2026-03-03

---

## Base URL

| Environment | URL |
|-------------|-----|
| Local dev   | `http://localhost:8000` |
| Production  | `https://api.neuralgto.com` (TBD) |

All endpoints are prefixed with `/api/`.

---

## Authentication

Not yet implemented. Planned: **Clerk** JWT in `Authorization: Bearer <token>` header.
Until then, endpoints are open but rate-limited (10 req/min per IP).

---

## Endpoints

### `GET /api/health`

Liveness and readiness check. No authentication required.

**Response — `200 OK`**

```json
{
  "status": "ok",
  "solver_available": true,
  "version": "0.1.0"
}
```

| Field              | Type    | Values                        |
|--------------------|---------|-------------------------------|
| `status`           | string  | `"ok"` \| `"degraded"` \| `"error"` |
| `solver_available` | boolean | Whether the TexasSolver binary is reachable |
| `version`          | string  | Semver API version            |

---

### `POST /api/analyze`

Run the full NeuralGTO analysis pipeline.

Rate limit: **10 requests/minute** per IP.

#### Request Body

The endpoint supports two input modes. At least `query` **or** `hero_hand` must be provided.

**Mode 1 — Natural Language:**

```json
{
  "query": "I have AKs on the BTN, 100bb deep. Villain opens 3bb from CO. What should I do?",
  "mode": "default",
  "opponent_notes": "Villain is tight and folds too much to 3-bets",
  "output_level": "advanced"
}
```

**Mode 2 — Structured (React card picker):**

```json
{
  "hero_hand": "AhKs",
  "hero_position": "BTN",
  "board": "Ts,9d,4h",
  "pot_size_bb": 12.5,
  "effective_stack_bb": 87.5,
  "villain_position": "CO",
  "mode": "default",
  "opponent_notes": "",
  "output_level": "advanced"
}
```

| Field               | Type   | Required | Default      | Description |
|---------------------|--------|----------|--------------|-------------|
| `query`             | string | No*      | `""`         | Free-text poker scenario |
| `hero_hand`         | string | No*      | `""`         | Hero's hole cards (e.g. `"AhKs"`) |
| `hero_position`     | string | No       | `""`         | Position enum: `UTG\|LJ\|HJ\|CO\|BTN\|SB\|BB` |
| `board`             | string | No       | `""`         | Community cards, comma-separated |
| `pot_size_bb`       | float  | No       | `null`       | Pot in big blinds (0–5000) |
| `effective_stack_bb` | float | No       | `null`       | Effective stack in bb (0–5000) |
| `villain_position`  | string | No       | `""`         | Villain's position |
| `mode`              | string | No       | `"default"`  | `"fast"` \| `"default"` \| `"pro"` |
| `opponent_notes`    | string | No       | `""`         | Villain tendencies (max 500 chars) |
| `output_level`      | string | No       | `"advanced"` | `"beginner"` \| `"advanced"` |

\* At least one of `query` or `hero_hand` must be provided.

#### Response — `200 OK`

```json
{
  "advice": "With AhKs on the BTN facing a CO open, you should 3-bet to ~9bb...",
  "source": "solver",
  "confidence": "high",
  "mode": "default",
  "cached": false,
  "solve_time": 12.4,
  "parse_time": 1.2,
  "output_level": "advanced",
  "sanity_note": "",
  "scenario": {
    "hero_hand": "AhKs",
    "hero_position": "BTN",
    "board": "Ts,9d,4h",
    "pot_size_bb": 12.5,
    "effective_stack_bb": 87.5,
    "current_street": "flop",
    "hero_is_ip": true,
    "num_players_preflop": 2,
    "game_type": "cash",
    "stack_depth_bb": 100.0,
    "oop_range": "22+,A2s+,K9s+,Q9s+,J9s+,T9s,98s,87s,76s,65s,ATo+,KTo+,QTo+,JTo",
    "ip_range": "22+,A2s+,K5s+,Q8s+,J8s+,T8s+,97s+,87s,76s,65s,A8o+,K9o+,Q9o+,J9o+,T9o"
  },
  "strategy": {
    "hand": "AhKs",
    "actions": {
      "CHECK": 0.12,
      "BET 67": 0.65,
      "BET 100": 0.23
    },
    "best_action": "BET 67",
    "best_action_freq": 0.65,
    "range_summary": {
      "CHECK": 0.40,
      "BET": 0.60
    },
    "source": "solver"
  },
  "structured_advice": {
    "top_plays": [
      {
        "action": "BET 67",
        "frequency": 0.65,
        "ev_signal": "positive",
        "explanation": "Betting 2/3 pot is the highest-EV line. AKs has strong equity on this board with two overcards and a backdoor flush draw..."
      },
      {
        "action": "BET 100",
        "frequency": 0.23,
        "ev_signal": "positive",
        "explanation": "A pot-sized bet puts maximum pressure..."
      },
      {
        "action": "CHECK",
        "frequency": 0.12,
        "ev_signal": "neutral",
        "explanation": "Checking is a low-frequency option used to protect the checking range..."
      }
    ],
    "street_reviews": {
      "preflop": "Standard 3-bet from BTN vs CO open.",
      "flop": "T-high board connects well with our range..."
    },
    "future_streets": "If called, plan to barrel on most turn cards except those that complete villain's draws.",
    "table_rule": "On T-high flops as the 3-bettor, c-bet frequently with overcards + backdoors.",
    "raw_advice": "Full unstructured text..."
  }
}
```

| Field              | Type    | Nullable | Description |
|--------------------|---------|----------|-------------|
| `advice`           | string  | No       | Full NL advice text |
| `source`           | string  | No       | `"solver"` \| `"gemini"` \| `"gpt_fallback"` \| `"validation_error"` |
| `confidence`       | string  | No       | `"low"` \| `"medium"` \| `"high"` |
| `mode`             | string  | No       | Mode used for this analysis |
| `cached`           | boolean | No       | Whether result was from cache |
| `solve_time`       | float   | No       | Solver time in seconds |
| `parse_time`       | float   | No       | Parser time in seconds |
| `output_level`     | string  | No       | Verbosity level used |
| `sanity_note`      | string  | No       | Optional sanity check note |
| `scenario`         | object  | Yes      | Parsed scenario (null on errors) |
| `strategy`         | object  | Yes      | Strategy result (null on errors) |
| `structured_advice`| object  | Yes      | Structured breakdown (null on errors) |

---

### `POST /api/board/update`

Re-analyse with a new turn or river card appended.

Rate limit: **10 requests/minute** per IP.

#### Request Body

```json
{
  "query": "I have AKs on the BTN, 100bb deep. Board is Ts9d4h.",
  "new_card": "Ah",
  "mode": "default",
  "opponent_notes": "",
  "output_level": "advanced"
}
```

| Field           | Type   | Required | Default      | Description |
|-----------------|--------|----------|--------------|-------------|
| `query`         | string | Yes      | —            | Original scenario text (min 10 chars) |
| `new_card`      | string | Yes      | —            | Card to add (e.g. `"Ah"`, `"9c"`) |
| `mode`          | string | No       | `"default"`  | Analysis mode |
| `opponent_notes`| string | No       | `""`         | Villain tendencies |
| `output_level`  | string | No       | `"advanced"` | Output verbosity |

#### Response — `200 OK`

Same schema as `POST /api/analyze`.

---

## Error Responses

All errors return a consistent envelope:

```json
{
  "detail": "Hero hand 'XYZ' is not a valid poker hand.",
  "error_code": "INVALID_HAND"
}
```

| Field        | Type   | Description |
|--------------|--------|-------------|
| `detail`     | string | Human-readable error message |
| `error_code` | string | Machine-readable code for programmatic handling |

### Error Codes

| Code               | HTTP Status | Meaning |
|--------------------|-------------|---------|
| `VALIDATION_ERROR` | 422         | Request body failed Pydantic validation |
| `INVALID_HAND`     | 422         | Hero hand is malformed or unrecognised |
| `INVALID_BOARD`    | 422         | Board cards are malformed |
| `INVALID_POSITION` | 422         | Position string is not a valid position |
| `PARSE_FAILED`     | 500         | Gemini NL parser failed to extract scenario |
| `SOLVER_TIMEOUT`   | 504         | Solver exceeded the configured timeout |
| `RATE_LIMITED`     | 429         | Too many requests from this IP |
| `INTERNAL_ERROR`   | 500         | Unexpected server error |

### HTTP Status Codes Used

| Status | Meaning |
|--------|---------|
| 200    | Success |
| 422    | Validation error (bad input) |
| 429    | Rate limited |
| 500    | Internal server error |
| 504    | Solver timeout |

---

## Analysis Modes

| Mode      | `use_solver` | Accuracy | Max Iterations | Timeout |
|-----------|:------------:|:--------:|:--------------:|:-------:|
| `fast`    | No (LLM-only) | —     | —              | —       |
| `default` | Yes          | 2%       | 100            | 120s    |
| `pro`     | Yes          | 0.3%     | 500            | 360s    |

---

## Strategy Source Values

| Value              | Meaning |
|--------------------|---------|
| `solver`           | Result computed by TexasSolver CFR |
| `gemini`           | Result from Gemini LLM (solver unavailable or preflop) |
| `gpt_fallback`     | Fallback LLM advice (solver error) |
| `validation_error` | Input was rejected before analysis |

---

## CORS

Allowed origins (configured in `backend/main.py`):

- `https://neuralgto.vercel.app`
- `https://neuralgto.pages.dev`
- `http://localhost:5173` (Vite dev server)

Methods: `GET`, `POST`, `OPTIONS`

---

## Rate Limiting

- **10 requests/minute** per IP via `slowapi`
- Returns `429` with `{"detail": "Rate limit exceeded. Try again in a minute."}`
- Future: Clerk-authenticated users get higher limits

---

## Notes for Frontend Developers

1. **Always validate responses** with the Zod schemas in `frontend/src/types/api.ts`.
2. **Check `source` field** — if it's `"validation_error"`, show the `advice` text as an error message, not as strategy advice.
3. **Nullable fields** — `scenario`, `strategy`, and `structured_advice` are all nullable. Handle `null` gracefully (show a fallback UI).
4. **Solver timing** — `solve_time` can be 0 (fast mode / cached) or up to 120s (default) or 360s (pro). Show a loading spinner.
5. **Frequency display** — Frequencies in `actions` are 0–1 floats. Display as percentages with 1 decimal: `(freq * 100).toFixed(1) + "%"`.
6. **EV signals** — Map `ev_signal` to colours: `positive` → emerald-400, `negative` → rose-400, `neutral` → amber-400.
