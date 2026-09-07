"""Keep compose.yaml and the production quadlets on the same image tags.

compose.yaml is the source of truth because dependabot understands it and has no concept of
quadlet files. This test is what stops a dependabot bump from landing in dev while production
quietly stays behind, which is how emqx ended up at 5.10.3 in compose and 6.3.0 in the
quadlets.
"""

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE = REPO_ROOT / "compose.yaml"
QUADLET_DIR = REPO_ROOT / "config" / "quadlet"

# Services built from this repo, whose tag is a deploy-time variable rather than a pin.
BRIDGER_SERVICES = {"bridger", "bot", "http"}


def normalize(image: str) -> str:
    """docker.io/library/influxdb:2.8.0 and influxdb:2.8.0 are the same image."""
    image = re.sub(r"^docker\.io/(library/)?", "", image)
    return image


def compose_images() -> dict[str, str]:
    services = yaml.safe_load(COMPOSE.read_text())["services"]
    return {
        name: normalize(service["image"])
        for name, service in services.items()
        if name not in BRIDGER_SERVICES and "image" in service
    }


def quadlet_images() -> dict[str, str]:
    images = {}

    for path in QUADLET_DIR.glob("*.container"):
        if path.stem in BRIDGER_SERVICES:
            continue

        for line in path.read_text().splitlines():
            if line.strip().startswith("Image"):
                images[path.stem] = normalize(line.split("=", 1)[1].strip())
                break

    return images


@pytest.mark.parametrize("service", sorted(set(compose_images()) & set(quadlet_images())))
def test_compose_and_quadlet_agree(service):
    assert compose_images()[service] == quadlet_images()[service], (
        f"{service} differs between compose.yaml and config/quadlet/{service}.container"
    )


def test_every_shared_service_is_compared():
    # Guards the test above from silently comparing nothing if a name drifts.
    shared = set(compose_images()) & set(quadlet_images())

    assert {"emqx", "influxdb", "grafana", "loki", "alloy", "certbot"} <= shared
