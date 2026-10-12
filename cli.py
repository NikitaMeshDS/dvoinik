"""CLI: прогон сценария и (опционально) валидация против живого опроса.

python cli.py student_card --n 200 --mock
python cli.py student_card --n 200 --survey data/survey.csv
"""
import argparse
import json

from dvoinik.engine import simulate
from dvoinik.population import build_population
from dvoinik.scenarios import SCENARIOS
from dvoinik.validate import compare, load_survey

p = argparse.ArgumentParser()
p.add_argument("scenario", choices=list(SCENARIOS))
p.add_argument("--n", type=int, default=200)
p.add_argument("--mock", action="store_true", help="без LLM, эвристическая модель")
p.add_argument("--survey", help="CSV с ответами живых респондентов: segment,variant,decision")
a = p.parse_args()

sc = SCENARIOS[a.scenario]
rep = simulate(build_population(a.n, sc["population"]), sc, mock=a.mock)
for vid, r in rep.items():
    print(f"\nВариант {vid}: конверсия {r['conversion']:.0%}")
    for s in r["segments"].values():
        print(f"  {s['name']:<42} {s['conversion']:>5.0%}  (n={s['n']})")
    print("  Причины отказа:", json.dumps(r["objections"], ensure_ascii=False))
if a.survey:
    print("\nВалидация:", compare(rep, load_survey(a.survey)))
