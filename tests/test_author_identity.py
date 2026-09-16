"""Keep historical local identities mapped to the verified repository author."""

from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = "Hoang Duong <279267588+hoangduong6210@users.noreply.github.com>"


@pytest.mark.parametrize(
    "historical_identity",
    [
        "Hoang Duong <Hoangduong4316@gmail.com>",
        "Hoang Duong <Hoangduong4316@icloud.com>",
        "Duong Viet Hoang <duongviethuy6210@gmail.com>",
        "Duong Viet Hoang <Hoangduong4316@icloud.com>",
        CANONICAL,
    ],
)
def test_project_author_aliases_resolve_to_verified_account(
    historical_identity: str,
) -> None:
    result = subprocess.run(
        ["git", "check-mailmap", historical_identity],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == CANONICAL
