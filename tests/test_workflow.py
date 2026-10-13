"""Checks the exported n8n workflow, since a typo there only shows up after importing it."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WORKFLOW = json.loads((Path(__file__).parents[1] / "workflows" / "price-watch.json").read_text("utf-8"))
NODES = {n["name"]: n for n in WORKFLOW["nodes"]}
SENDERS = ["Send to Discord", "Push to my phone", "Send on WhatsApp"]


def test_every_connection_points_to_a_real_node():
    for source, outputs in WORKFLOW["connections"].items():
        assert source in NODES
        for branch in outputs["main"]:
            for target in branch:
                assert target["node"] in NODES


def reaches(name, goal):
    if name == goal:
        return True
    nxt = WORKFLOW["connections"].get(name, {}).get("main", [[]])
    return any(reaches(t["node"], goal) for branch in nxt for t in branch)


@pytest.mark.parametrize("sender", SENDERS)
def test_both_triggers_reach_every_sender(sender):
    assert reaches("Every day at 9", sender)
    assert reaches("Run by hand", sender)


@pytest.mark.parametrize("sender", SENDERS)
def test_each_sender_only_runs_when_its_setting_is_there(sender):
    # the node right before each sender is an IF on an env var
    (gate,) = [name for name, out in WORKFLOW["connections"].items()
               if any(t["node"] == sender for branch in out["main"] for t in branch)]
    assert NODES[gate]["type"] == "n8n-nodes-base.if"
    assert "$env." in json.dumps(NODES[gate]["parameters"])


def test_no_secret_in_the_json():
    text = json.dumps(WORKFLOW)
    assert NODES["Send to Discord"]["parameters"]["url"] == "={{ $env.DISCORD_WEBHOOK_URL }}"
    assert "discord.com/api/webhooks" not in text
    assert "$env.WHATSAPP_APIKEY" in text
    assert "apikey=" not in text


def run_code_node(deals):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    # same idea as n8n: the code is the body of an async function with $input in scope
    js = (
        "const $input = { first: () => ({ json: { deals: %s } }) };\n"
        "(async () => { %s })().then(r => console.log(JSON.stringify(r)));"
    ) % (json.dumps(deals), NODES["Write the message"]["parameters"]["jsCode"])
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def deal(name, price, full, discount, lowest=False, old=None):
    return {"appid": 1, "name": name, "url": f"https://store.steampowered.com/app/{name}/", "image": "https://img/h.jpg",
            "currency": "BRL", "price": price, "old_price": old or full, "full_price": full,
            "discount": discount, "lowest": lowest}


def test_code_node_stops_when_there_are_no_deals():
    assert run_code_node([]) == []


def test_code_node_messages():
    (item,) = run_code_node([deal("Red Dead Redemption 2", 7497, 29990, 75),
                             deal("Hades II", 7119, 8899, 0, lowest=True)])
    out = item["json"]
    assert out["title"] == "2 games from the list are cheaper"
    first = out["discord"]["embeds"][0]
    assert first["title"] == "Red Dead Redemption 2"
    assert first["description"] == "R$ 74,97 (-75%, was R$ 299,90)."
    assert first["image"]["url"] == "https://img/h.jpg"
    assert "Hades II: R$ 71,19 (was R$ 88,99). Lowest since I started watching." in out["push"]["message"]
    assert out["push"]["click"].endswith("/app/Red Dead Redemption 2/")
    assert "*Red Dead Redemption 2* R$ 74,97" in out["whatsapp"]


def test_code_node_keeps_the_limits():
    (item,) = run_code_node([deal("A" * 80, 100, 200, 50)] * 60)
    out = item["json"]
    assert len(out["discord"]["embeds"]) == 10
    assert len(out["whatsapp"]) <= 1505


def test_expressions_avoid_spread():
    # n8n 1.64's expression parser chokes on "...": the phone push never left in CI
    for node in WORKFLOW["nodes"]:
        for value in json.dumps(node["parameters"]).split('"'):
            if value.startswith("={{"):
                assert "..." not in value, node["name"]


def test_code_node_target_without_a_sale():
    d = deal("Hollow Knight: Silksong", 5999, 5999, 0)
    d.update(target=6000, below_target=True)
    (item,) = run_code_node([d])
    out = item["json"]
    assert out["title"] == "Hollow Knight: Silksong is under your target"
    assert out["discord"]["embeds"][0]["description"] == "R$ 59,99. Under your target of R$ 60,00."
