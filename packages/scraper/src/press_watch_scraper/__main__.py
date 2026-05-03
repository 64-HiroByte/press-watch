import logging

LOGGER = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    LOGGER.info("PressWatch scraper is ready. Fetching will be implemented later.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
