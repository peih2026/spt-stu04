# investigation-agent

This repository contains the `investigation-agent` used to analyze projects, run local tools, and produce investigation reports.

Usage

1. Install dependencies:

```
python -m pip install -r requirements.txt
```

2. Run the agent (set required env vars, e.g. DEEPSEEK_API_KEY, GITHUB_TOKEN):

```
python agent.py
```

Reports are written to the `reports/` directory.
