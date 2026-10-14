# Enterprise agent

Agent for the ERC3 company API benchmark. It searches employees, projects and customers, reads wiki pages and submits structured task responses.

The implementation combines OpenAI-generated Python, API helpers and role context. `store_agent.py` contains the structured-response variant.

## Run

Requires Python 3.11+, OpenAI credentials and an ERC3 benchmark account.

```sh
python -m venv .venv
python -m pip install -r requirements.txt
python main.py --benchmark erc3-prod --workspace my --model YOUR_MODEL
```

Use the virtual environment's Python. Set `OPENAI_API_KEY` and `ERC3_API_KEY` in the process environment. `.env.example` lists the required variables; the application does not load it automatically.

Use `--specs id1,id2` to run selected tasks and `--flags ""` to omit competition flags.

Each run writes task scores, durations and evaluation details to `logs/runs/`. These files are excluded from Git.

```sh
python -m unittest -v test_access
```

Generated Python executes in the agent process. Run this prototype with trusted benchmark tasks and restricted API credentials. The API remains responsible for authorization; this repository does not provide a production sandbox.
