"""Enable the approved synchronization settings without replacing credentials."""

import argparse
import os
from pathlib import Path

from dotenv import set_key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("env_file", type=Path)
    args = parser.parse_args()
    target = args.env_file.resolve(strict=True)
    mode = target.stat().st_mode
    for key, value in {
        "DINGTALK_STREAM_ENABLED": "true",
        "DINGTALK_REQUEST_INTERVAL": "0.05",
        "LEAVE_SYNC_VERIFY_VACATION": "true",
        "EVENT_POLL_SECONDS": "5",
    }.items():
        set_key(str(target), key, value, quote_mode="never")
    os.chmod(target, mode)
    print("Synchronization settings updated; existing credentials preserved")


if __name__ == "__main__":
    main()
