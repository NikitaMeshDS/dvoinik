"""Подготовить случайную последовательность бланков A/B для опроса по вкладу."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
from collections import defaultdict
from io import StringIO
from pathlib import Path
from random import SystemRandom

from dvoinik.validate import SurveyRates


def csv_rows(text, fields):
    reader = csv.reader(StringIO(text, newline=""), strict=True)
    if next(reader, None) != fields:
        raise ValueError(f"Ожидаются столбцы {', '.join(fields)}.")
    for row in reader:
        if not row:
            continue
        if len(row) != len(fields):
            raise ValueError(f"Строка {reader.line_num}: неверное число столбцов.")
        yield reader.line_num, [value.strip() for value in row]


def reconcile(assignments_path, responses_path, groups, expected_sha256=None):
    raw = assignments_path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and checksum != expected_sha256.lower():
        raise ValueError("SHA-256 списка назначений отличается от зафиксированного.")
    counts = {
        variant: dict.fromkeys(("planned", "issued", "valid", "missing", "unclassified"), 0)
        for variant in ("A", "B")
    }
    assignments = {}
    for index, (_, (slot, variant)) in enumerate(csv_rows(raw.decode("utf-8-sig"), ["slot", "variant"]), 1):
        if slot != str(index) or variant not in counts:
            raise ValueError("Список назначений должен содержать позиции по порядку и варианты A/B.")
        assignments[slot] = variant
        counts[variant]["planned"] += 1
    if not assignments or counts["A"]["planned"] != counts["B"]["planned"]:
        raise ValueError("В списке назначений должно быть поровну A и B.")

    seen = set()
    cells = defaultdict(lambda: [0, 0])
    for line, (slot, group, decision) in csv_rows(
        responses_path.read_text(encoding="utf-8-sig"), ["slot", "segment", "decision"]
    ):
        if slot not in assignments:
            raise ValueError(f"Строка {line}: позиции нет в списке назначений.")
        if slot in seen:
            raise ValueError(f"Строка {line}: позиция повторяется.")
        if (group and group not in groups) or decision not in {"", "0", "1"}:
            raise ValueError(f"Строка {line}: неверный сегмент или ответ.")
        seen.add(slot)
        variant = assignments[slot]
        counts[variant]["issued"] += 1
        if not decision:
            counts[variant]["missing"] += 1
        elif not group:
            counts[variant]["unclassified"] += 1
        else:
            counts[variant]["valid"] += 1
            cell = cells[variant, group]
            cell[0] += int(decision)
            cell[1] += 1
    if seen != {str(index) for index in range(1, len(seen) + 1)}:
        raise ValueError("Регистр выдачи должен начинаться с позиции 1 и идти без пропусков позиций.")
    survey = SurveyRates(
        {key: yes / n for key, (yes, n) in cells.items()}, {key: n for key, (_, n) in cells.items()}
    )
    return survey, {"assignments_sha256": checksum, "counts": counts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--n-per-variant", type=int, required=True, help="Плановое число назначений на бланк")
    parser.add_argument("--output", type=Path, required=True, help="Новый CSV со столбцами slot и variant")
    args = parser.parse_args()
    if not 1 <= args.n_per_variant <= 10000:
        parser.error("--n-per-variant должен быть от 1 до 10 000.")

    variants = ["A", "B"] * args.n_per_variant
    SystemRandom().shuffle(variants)
    try:
        with open(
            args.output,
            "x",
            newline="",
            encoding="utf-8",
            opener=lambda path, flags: os.open(path, flags, 0o600),
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow(("slot", "variant"))
            writer.writerows(enumerate(variants, 1))
        fingerprint = hashlib.sha256(args.output.read_bytes()).hexdigest()
    except FileExistsError:
        parser.exit(1, "Файл назначений уже существует. Укажите новый путь.\n")
    except OSError:
        parser.exit(1, "Не удалось записать или проверить файл назначений. Проверьте путь и права доступа.\n")

    print(f"Записано {len(variants)} назначений, по {args.n_per_variant} на вариант.")
    print(f"SHA-256 {fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
