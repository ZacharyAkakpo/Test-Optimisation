"""Lancement : python -m infra_optimizer [--input data/rapport.json] [--output output.json] [--no-llm]"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from .graph import run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m infra_optimizer")
    parser.add_argument("--input", default="data/rapport.json", help="fichier de relevés JSON")
    parser.add_argument("--output", default="output.json", help="rapport à produire")
    parser.add_argument("--no-llm", action="store_true", help="n'utiliser que le catalogue de règles")
    args = parser.parse_args(argv)

    load_dotenv()  # lit ANTHROPIC_API_KEY dans un fichier .env s'il existe
    sys.stdout.reconfigure(encoding="utf-8")  # accents corrects dans la console Windows
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout)

    try:
        state = run_pipeline(args.input, use_llm=not args.no_llm)
    except (OSError, ValueError) as error:  # fichier absent, JSON invalide, aucun relevé valide
        logging.error(error)
        return 1

    report = state["report"]
    Path(args.output).write_text(report.model_dump_json(indent=2), encoding="utf-8")
    logging.info(
        "%d anomalies, %d recommandations (source : %s) -> %s",
        len(report.anomalies), len(report.recommendations), state["source"], args.output,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
