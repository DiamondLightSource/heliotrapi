import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(asctime)s %(name)s: %(message)s",
    datefmt="%H:%M:%S %d-%m-%Y",
)
logger = logging.getLogger(__name__)
