\# SizeRight



\*\*Tool-calling LLM agent for heat pump sizing.\*\* Describe a home in plain words and get a heating and cooling load, a recommended size, backup heat needs and a balance point, with every number computed by tested Python, not by the model.



!\[SizeRight answering a sizing question](docs/demo.png)



\## Why



"What size heat pump do I need?" is the first question every buyer asks, and the answer usually waits for a site visit. An oversized unit short-cycles; an undersized one leans on expensive backup heat. SizeRight gives a fast, explainable first estimate.



\## How it works



```

User message ──> LLM (Qwen 2.5 7B via Ollama, or GitHub Models)

&#x20;                  │  extracts facts, decides when it has enough

&#x20;                  ▼

&#x20;           tool call: size\_heat\_pump(floor\_area\_ft2, insulation, air\_tightness, city, ...)

&#x20;                  │

&#x20;                  ▼

&#x20;           sizing.py  (deterministic, unit-tested)

&#x20;             1. design temperatures for the city

&#x20;             2. heating + cooling loads (U·A·ΔT + infiltration + gains)

&#x20;             3. size from a 1.5–5 ton ladder, backup heat, balance point

&#x20;                  │

&#x20;                  ▼

&#x20;           JSON result ──> LLM explains it ──> Chainlit UI (tool call shown)

```



The model never does arithmetic. It gathers inputs and explains outputs; every number traces back to `sizing.py`, and each tool call is shown in the UI:



!\[Expanded tool call with arguments and result](docs/tool-call.png)



\## Sample results



| Home | City | Heating load | Cooling load | Recommendation |

|---|---|---|---|---|

| Drafty 1950s ranch, 1,400 ft² | Minneapolis, MN | 72,711 Btu/h | 23,251 Btu/h | 5 tons + 11.0 kW backup |

| Tight new build, 2,400 ft², 2 floors | Denver, CO | 23,530 Btu/h | 22,718 Btu/h | 3 tons |

| Average colonial, 2,000 ft², 2 floors | Boston, MA | 31,405 Btu/h | 22,297 Btu/h | 4 tons |

| Average home, 1,800 ft² | Phoenix, AZ | 15,544 Btu/h | 27,377 Btu/h | 2.5 tons (cooling-led) |



\## Method (simplified)



\- \*\*Envelope:\*\* square footprint; U-values for poor, average and good insulation

\- \*\*Infiltration:\*\* 1.0, 0.5 or 0.25 air changes per hour; load = 1.08 × CFM × ΔT

\- \*\*Indoor setpoints:\*\* 70 °F heating, 75 °F cooling

\- \*\*Cooling extras:\*\* window solar gain, people and appliances, 1.3× latent factor

\- \*\*Heat pump capacity:\*\* rated at 47 °F, falling linearly to 70% at 5 °F (configurable)

\- \*\*Sizing:\*\* heating-led climates size for capacity at the design temperature; cooling-led climates size for cooling load



\## Run it



```bash

git clone https://github.com/Shriya-Padhi/size-right.git

cd size-right

python -m venv .venv

source .venv/bin/activate          # Windows Git Bash: source .venv/Scripts/activate

pip install -r requirements.txt

cp .env.example .env               # choose Ollama or GitHub Models

ollama pull qwen2.5:7b             # skip if using GitHub Models

chainlit run app.py -w             # http://localhost:8000

```



\## Tests



```bash

python -m pytest -v                # 11 tests, no model or network needed

```



\- \*\*Engine tests:\*\* physics direction, invariants (the breakdown sums to the total), capacity-curve boundaries and input validation

\- \*\*Agent tests:\*\* a mocked LLM client checks the tool-call loop and message protocol



\## Project structure



| File | Purpose |

|---|---|

| `sizing.py` | Load calculation and size recommendation |

| `agent.py` | System prompt, tool schemas, tool runner, function-calling loop |

| `app.py` | Chainlit chat UI with tool calls shown as steps |

| `data/design\_temps.csv` | Sample design temperatures for 21 US cities |

| `tests/` | Engine tests and mocked-LLM agent tests |



\## Limits



\- \*\*Not a Manual J.\*\* This is an educational first estimate; real sizing needs a room-by-room calculation and a site visit.

\- \*\*Sample climate data.\*\* Design temperatures are approximate. Use official ASHRAE or ACCA design data for real work.

\- \*\*Small-model explanation errors.\*\* With Qwen 2.5 7B, the numbers are always correct (they come from code), but explanations sometimes slip, e.g. describing the balance point as a heating-to-cooling switch, or converting units on its own. Larger models follow the prompt more closely.

\- \*\*Speed.\*\* Local CPU inference takes about 30 seconds to 2 minutes per answer; GitHub Models takes a few seconds.



\## Next steps



\- Stream tokens to the UI and add a capacity-vs-temperature chart

\- Tighten the prompt and add output checks for balance-point wording

\- Load real equipment specs to recommend specific models

\- Show which upgrade (air sealing, insulation) cuts the most load



\## License



MIT

