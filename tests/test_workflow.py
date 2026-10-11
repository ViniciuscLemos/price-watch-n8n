"""Checks the exported n8n workflow, since a typo there only shows up after importing it."""

import json
import subprocess
from pathlib import Path

import pytest

WORKFLOW = json.loads((Path(__file__).parents[1] / "workflows" / "price-watch.json").read_text("utf-8"))
NODES = {n["name"]: n for n in WORKFLOW["nodes"]}


def test_every_connection_points_to_a_real_node():
    for source, outputs in WORKFLOW["connections"].items():
        assert source in NODES
        for branch in outputs["main"]:
            for target in branch:
                assert target["node"] in NODES


def test_both_triggers_reach_discord():
    def reaches(name, goal):
        if name == goal:
            return True
        nxt = WORKFLOW["connections"].get(name, {}).get("main", [[]])
        return any(reaches(t["node"], goal) for branch in nxt for t in branch)

    assert reaches("Every day at 9", "Send to Discord")
    assert reaches("Run by hand", "Send to Discord")


def test_no_secret_in_the_json():
    assert NODES["Send to Discord"]["parameters"]["url"] == "={{ $env.DISCORD_WEBHOOK_URL }}"
    assert "discord.com/api/webhooks" not in json.dumps(WORKFLOW)


def run_code_node(changes):
    node = shutil_which("node")
    if not node:
        pytest.skip("node not installed")
    # same idea as n8n: the code is the body of an async function with $input in scope
    js = (
        "const $input = { first: () => ({ json: { changes: %s } }) };\n"
        "(async () => { %s })().then(r => console.log(JSON.stringify(r)));"
    ) % (json.dumps(changes), NODES["Write the message"]["parameters"]["jsCode"])
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def shutil_which(name):
    import shutil
    return shutil.which(name)


def test_code_node_stops_when_nothing_changed():
    assert run_code_node([]) == []


def test_code_node_message():
    items = run_code_node([
        {"kind": "price_drop", "title": "Soumission", "price": 45.1, "old_price": 50.1, "url": "https://x/1"},
        {"kind": "back_in_stock", "title": "Sharp Objects", "price": 47.82, "url": "https://x/2"},
    ])
    msg = items[0]["json"]["message"]
    assert "**Soumission** £50.10 -> £45.10" in msg
    assert "Back in stock: **Sharp Objects** (£47.82)" in msg
    assert items[0]["json"]["count"] == 2


def test_code_node_keeps_discord_limit():
    many = [{"kind": "back_in_stock", "title": "A" * 80, "price": 1, "url": "https://x"}] * 60
    assert len(run_code_node(many)[0]["json"]["message"]) <= 2000
