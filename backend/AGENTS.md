# Repository instructions

- Run commands from the repository root in an isolated environment installed with `pip install -e '.[test]'`.
- Validate changes with `pytest -q`. (The published `results/` artifacts and `benchmarks/verify_published.py` inputs are not included in this checkout.)
- Benchmark outputs are create-only. Use a new output path and expose exactly one CUDA GPU per scorer process.
- Do not change headline claims in the docs without regenerating and committing the supporting row-level evidence and updating the method/results text.
- Preserve exact model and source revisions. Use `benchmarks/fetch_sources.py` only for its listed redistributable inputs; do not commit model weights, caches, or third-party raw records.
- The `remote` backend must keep stdlib-only HTTP (including the dotenv loader), `.env`-file config with CLI overrides, explicit probability limitations, and loud failures when the host server omits option logprobs. Never commit `.env` or secrets.
