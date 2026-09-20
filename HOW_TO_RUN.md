# SemIf (OpenJev) — Overview & Run Guide

SemIf is an open baseline and reproduction of the interface pattern used by TypeSafe's Jev service for runtime-defined semantic decisions ("semantic `if`s").

Instead of asking an LLM to generate natural language or JSON and then parsing that text back into programmatic control flow (e.g. `{"route": "billing"}`), SemIf extracts decision probabilities **directly from the model's native next-token logits / logprobs** in a single forward pass without autoregressive generation loops.

---

## Core Components

The implementation lives in [`backend/src/semif_phase1/`](backend/src/semif_phase1/):

1. **Remote Backend** ([`remote.py`](backend/src/semif_phase1/remote.py)): Uses OpenAI-compatible HTTP endpoints (`/v1/chat/completions`) that return logprobs (LM Studio, Ollama, vLLM). Single-letter answer slots (`A`–`P`) are scored and normalized via softmax over declared options.
2. **PyTorch Backend** ([`direct.py`](backend/src/semif_phase1/direct.py), [`serial.py`](backend/src/semif_phase1/serial.py), [`shared.py`](backend/src/semif_phase1/shared.py), [`reranker.py`](backend/src/semif_phase1/reranker.py)): Local CUDA/PyTorch inference on Hugging Face weights (e.g. `Qwen/Qwen3.5-4B`).
3. **Local Web UI** ([`server.py`](backend/src/semif_phase1/server.py)): Zero-dependency single-page web app to test decisions interactively.
4. **Jev Choice Server** ([`jev_server.py`](backend/src/semif_phase1/jev_server.py)): Drop-in server answering TypeSafe's Jev API contract (`POST /v1/systemone` and `POST /v1/choices`) backed by an open hosted model.
5. **TypeSafe Proxy** ([`typesafe_proxy.py`](backend/src/semif_phase1/typesafe_proxy.py)): Reverse proxy for real TypeSafe API keys with client authentication and retry backoff.

---

## Environment & Configuration

- Configuration is controlled via [`backend/.env`](backend/.env) (refer to [`backend/.env.example`](backend/.env.example) for options).
- LM Studio / remote configuration defaults:
  ```bash
  SEMIF_REMOTE_BASE_URL=http://localhost:1234/v1
  SEMIF_REMOTE_MODEL=qwen3.5-4b
  SEMIF_REMOTE_REVISION=lm-studio-local
  SEMIF_REMOTE_API_KEY=lm-studio
  SEMIF_REMOTE_REASONING_EFFORT=none
  ```

---

## How to Run

All commands should be executed from the `backend/` directory.

### 1. Run the Test Suite
To verify the environment and test coverage:
```bash
cd backend
pytest -q
```

---

### 2. Run the CLI Decision Scorer (`semif-score`)
Score decision batches from a JSONL file (such as [`examples/decisions.jsonl`](backend/examples/decisions.jsonl)) using the remote LM Studio backend:

```bash
cd backend
python3 -m semif_phase1.cli \
  --backend remote \
  --mode direct \
  --input examples/decisions.jsonl \
  --output results-remote.jsonl
```
*(Or use `semif-score --backend remote --mode direct --input examples/decisions.jsonl --output results-remote.jsonl` if entrypoints are added to your PATH).*

Each output row contains the normalized probabilities, logits, forward timing, prompt hash, and model provenance.

---

### 3. Run the Interactive Web UI (`semif-ui`)
Launch the browser UI to test decisions interactively:

```bash
cd backend
python3 -m semif_phase1.server --port 8080
```
Open **`http://127.0.0.1:8080`** in your browser. You can enter an unstructured state, a question, and 2–16 candidate options; clicking **Score decision** computes and visualizes option probabilities in real-time.

---

### 4. Run the TypeSafe Jev Choice Server (`semif-jevsrv`)
To run a drop-in choice server compatible with TypeSafe Jev clients (such as browser automation agents like `jev-ultrafast`):

```bash
cd backend
python3 -m semif_phase1.jev_server --port 8090
```
The server answers at:
- `POST http://127.0.0.1:8090/v1/systemone`
- `POST http://127.0.0.1:8090/v1/choices`

#### Example Request:
```bash
curl -X POST http://127.0.0.1:8090/v1/choices \
  -H 'Content-Type: application/json' \
  -d '{
    "state": "Customer says their password reset email never arrived.",
    "questions": {
      "queue": {
        "type": "choice",
        "instructions": {"goal": "Route customer issue to correct support department"},
        "criteria": {
          "access": "Account access and login problems",
          "billing": "Invoices and subscription payment",
          "sales": "Product inquiries and upgrades"
        }
      }
    }
  }'
```

---

### 5. Run the TypeSafe Proxy (`semif-proxy`)
If you have an official TypeSafe API key and want to run a local gateway with key rotation and retry logic:

1. Add your key to [`backend/.env`](backend/.env):
   ```bash
   TYPESAFE_API_KEY=your_key_here
   ```
2. Generate a local client API key:
   ```bash
   cd backend
   python3 -m semif_phase1.typesafe_proxy --generate-key
   ```
3. Start the proxy:
   ```bash
   python3 -m semif_phase1.typesafe_proxy --port 4001
   ```

---

### 6. Run via Native PyTorch on Local GPU
If you wish to load model weights directly into CUDA memory rather than querying LM Studio:

```bash
cd backend
CUDA_VISIBLE_DEVICES=0 python3 -m semif_phase1.cli \
  --backend torch \
  --mode direct \
  --model Qwen/Qwen3.5-4B \
  --revision 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a \
  --input examples/decisions.jsonl \
  --output results.jsonl
```
> **Note:** PyTorch direct inference with `Qwen3.5-4B` requires around 8 GB of VRAM in BF16. For machines with 6 GB VRAM or when LM Studio is already hosting the model, `--backend remote` is recommended.

---

### 7. Verify Benchmark Claims
To run automated verification of the published benchmark metrics:
```bash
cd backend
python3 benchmarks/verify_published.py
(cd results/raw && sha256sum -c SHA256SUMS)
```
