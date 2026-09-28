# 001 - OpenAI-retained swap, NL-to-SQL, docs audit, guardrail test

## Goals
1. Replace the previous LLM client in `explain_with_ai()` with the Anthropic SDK (`claude-sonnet-5`), behavior unchanged.
2. Add "Ask the data": question -> Claude generates SQL -> executed as the read-only SA -> IAM rejects writes with 403.
3. Audit README.md, the app.py docstring and the SA description in main.tf so every claim matches the code.
4. Extend `test_readonly.py` with a second test that drives `generate_sql()` end to end.
5. Commit and push (explicitly requested by the user).

## Design decisions
- IAM is the only guardrail. No Python filter on DELETE/UPDATE/INSERT/DROP, no SELECT-only check, no refusal instruction in the prompt. This is deliberate and commented in code.
- `get_client()` is not modified and no second client is created.
- Schema for the prompt is taken from `main.tf` (`google_bigquery_table.indicators`), not guessed.
- Model-facing logic moves to `nl_sql.py` (no Streamlit import) so `test_readonly.py` can import it without running UI code. `app.py` imports from it.
- `get_client()` is decorated with `st.cache_resource` and lives in `app.py`; `nl_sql.py` will take a client as a parameter (dependency injection) so the test can pass its own impersonated client built the same way.
- `ANTHROPIC_API_KEY` is read from the environment via `.env`. `.env.example` documents it. The real `.env` is not edited by me.
- No `requirements.txt` exists today although the README references it; create one from the actual imports.

## Steps
1. Show diff for the OpenAI-retained swap; apply only after approval.
2. Create `nl_sql.py` (`generate_sql`, `run_generated_sql`) and wire the "Ask the data" UI in `app.py`.
3. Update README, docstring, main.tf description (description-only change, no resource change).
4. Extend `test_readonly.py`.
5. Run tests, then commit and push.

## Verification
- `python test_readonly.py` (needs GCP ADC and an Anthropic key; run by the user if credentials are unavailable here).
- A grep for the old provider and model names over the repo (excluding venv, .git, .terraform) returns zero hits.
