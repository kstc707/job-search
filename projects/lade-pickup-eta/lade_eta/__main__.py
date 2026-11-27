"""Command line: python -m lade_eta {ingest,train,serve}"""
import argparse

from .logs import setup_logging
from .settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="lade_eta")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest", help="download, clean and load one city into PostgreSQL")
    ing.add_argument("--no-postgres", action="store_true", help="only download and run the quality checks")
    tr = sub.add_parser("train", help="train, evaluate, log to MLflow, save artifacts")
    tr.add_argument("--source", choices=["postgres", "csv"], default="postgres")
    tr.add_argument("--no-mlflow", action="store_true")
    sv = sub.add_parser("serve", help="run the API")
    sv.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.log_level)
    if args.cmd == "ingest":
        from . import ingest

        ingest.run(settings, to_postgres=not args.no_postgres)
    elif args.cmd == "train":
        from . import train

        train.run(settings, source=args.source, track=not args.no_mlflow)
    elif args.cmd == "serve":
        import uvicorn

        uvicorn.run("lade_eta.api:app", host="0.0.0.0", port=args.port, workers=settings.api_workers)


if __name__ == "__main__":
    main()
