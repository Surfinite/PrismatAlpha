"""Fetch replays from S3."""
import gzip
import json
import logging
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

S3_BASE = "http://saved-games-alpha.s3-website-us-east-1.amazonaws.com"

def code_to_filename(code: str) -> str:
    """Convert replay code to local filename. Uses raw code (no URL encoding)."""
    return f"{code}.json.gz"

def code_to_s3_url(code: str) -> str:
    """Convert replay code to S3 URL. URL-encodes + and @ characters."""
    encoded = code.replace("+", "%2B").replace("@", "%40")
    return f"{S3_BASE}/{encoded}.json.gz"

def fetch_replay(code: str, output_dir: Path) -> Path:
    """Download a replay from S3 to output_dir. Returns path to saved file.

    Skips download if file already exists.
    """
    filename = code_to_filename(code)
    output_path = output_dir / filename
    if output_path.exists():
        logger.debug(f"Already exists: {output_path}")
        return output_path
    logger.info(f"Fetching {code} from S3...")
    urllib.request.urlretrieve(code_to_s3_url(code), str(output_path))
    return output_path
