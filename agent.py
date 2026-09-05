ANIMAL_COST = {"COW": 400, "SHEEP": 500, "GOOSE": 300}
STRUCTURE_KIND = {"COW": "PASTURE", "SHEEP": "PASTURE", "GOOSE": "COOP"}
BUILD_OP = {"PASTURE": "BUILD_PASTURE", "COOP": "BUILD_COOP"}


def _gen_structures(n_cow, n_sheep, n_goose, shed_stop=(4, 4)):
    candidates = sorted(
        [(x, y) for x in range(5) for y in range(5) if (x, y) != shed_stop],
        key=lambda p: abs(p[0] - shed_stop[0]) + abs(p[1] - shed_stop[1])
    )
    structs = []
    i = 0
    for animal, n in (("COW", n_cow), ("SHEEP", n_sheep), ("GOOSE", n_goose)):
        kind = STRUCTURE_KIND[animal]
        for _ in range(n):
            structs.append({
                "pos": candidates[i], "animal": animal, "kind": kind,
                "build": BUILD_OP[kind], "cost": ANIMAL_COST[animal],
                "shed_stop": shed_stop,
            })
            i += 1
    return structs


# Locked-in mix from the version-3 harness sweep: 4 cow / 3 sheep / 8 goose
# (the 3:2:5 ratio at n_total=15), chosen for CONSISTENCY -- mean~48-50k,
# std~4k -- over a higher-mean but much wider-variance cow-heavy mix.
STRUCTURES = _gen_structures(n_cow=4, n_sheep=3, n_goose=8)
RESERVED = {s["pos"] for s in STRUCTURES}


def _structure_needs_attention(tile):
    if tile is None:
        return True
    if isinstance(tile, dict) and tile.get("kind") in ("PASTURE", "COOP"):
        if "animal" not in tile:
            return True
        if tile.get("yield_units", 0) > 0:
            return True
        if not tile.get("fed_today"):
            return True
        if not tile.get("cared_today"):
            return True
        if tile.get("fertilizer_available"):
            return True
    return False


def _walk_toward(pos, dest):
    x, y = pos
    rx, ry = dest
    if x < rx:
        return ["EAST"]
    if x > rx:
        return ["WEST"]
    if y < ry:
        return ["SOUTH"]
    if y > ry:
        return ["NORTH"]
    return None


def _keeper_action(pos, tile, inv, shed, target_pos, shed_stop, animal, kind, build_op):
    if tile is None:
        step = _walk_toward(pos, target_pos)
        return step if step else [build_op]
    if isinstance(tile, dict) and tile.get("kind") == kind:
        if "animal" not in tile:
            if inv.get(animal, 0) > 0:
                step = _walk_toward(pos, target_pos)
                return step if step else ["PLACE", animal]
            if shed.get(animal, 0) > 0:
                step = _walk_toward(pos, shed_stop)
                return step if step else ["PICKUP", animal, 1]
            return ["PASS"]
        if tile.get("yield_units", 0) > 0:
            step = _walk_toward(pos, target_pos)
            return step if step else ["HARVEST"]
        if not tile.get("fed_today"):
            if inv.get("WHEAT", 0) > 0:
                step = _walk_toward(pos, target_pos)
                return step if step else ["FEED"]
            if shed.get("WHEAT", 0) > 0:
                step = _walk_toward(pos, shed_stop)
                return step if step else ["PICKUP", "WHEAT", 1]
            return ["PASS"]
        if not tile.get("cared_today"):
            step = _walk_toward(pos, target_pos)
            return step if step else ["CARE"]
        if tile.get("fertilizer_available"):
            step = _walk_toward(pos, target_pos)
            return step if step else ["COLLECT_FERTILIZER"]
        return ["PASS"]
    return ["PASS"]


def _idle_crop_action(pos, tile, seeds, inv, day, core_done):
    x, y = pos
    if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == "TOMATO":
        if inv.get("FERTILIZER", 0) > 0 and tile.get("fertilized_until_day", -1) < day:
            return ["FERTILIZE"]
        if not tile.get("watered_today"):
            return ["WATER"]
        if tile.get("yield_units", 0) > 0:
            return ["HARVEST"]
        return ["PASS"]
    if core_done and tile is None and (x, y) not in RESERVED and seeds.get("TOMATO", 0) > 0:
        return ["PLANT", "TOMATO"]
    if y % 2 == 0:
        if x < 4:
            return ["EAST"]
        return ["SOUTH"] if y < 4 else ["NORTH"]
    else:
        if x > 0:
            return ["WEST"]
        return ["SOUTH"] if y < 4 else ["NORTH"]


def my_agent(obs):
    HANDS_PER_DAY = len(STRUCTURES) - 1  # farmer + hands == one keeper per structure
    ANIMAL_RESERVE = 500
    WHEAT_BUY_BUFFER = 20
    TOMATO_SEED_TARGET = 6

    player = obs["player"]
    farm = obs["farms"][player]
    tiles = farm["tiles"]
    private = obs["private"]
    seeds = private["seeds"]
    shed = private["shed"]
    money = farm["money"]
    day = obs["day"]

    core_done = all(
        isinstance(tiles[s["pos"][1]][s["pos"][0]], dict) and tiles[s["pos"][1]][s["pos"][0]].get("animal") == s["animal"]
        for s in STRUCTURES
    )

    market_orders = []
    if obs["hour"] == 0:
        wheat_have = shed.get("WHEAT", 0)
        if wheat_have < WHEAT_BUY_BUFFER and money > 500:
            market_orders.append(["BUY_PRODUCT", "WHEAT", WHEAT_BUY_BUFFER - wheat_have])

        demand = {}
        for s in STRUCTURES:
            sx, sy = s["pos"]
            t = tiles[sy][sx]
            placed = isinstance(t, dict) and t.get("animal") == s["animal"]
            if not placed:
                demand[s["animal"]] = demand.get(s["animal"], 0) + 1
        for animal, needed in demand.items():
            have = shed.get(animal, 0)
            cost = ANIMAL_COST[animal]
            to_buy = min(1, needed - have)
            for _ in range(to_buy):
                if money > cost + ANIMAL_RESERVE:
                    market_orders.append(["BUY_ANIMAL", animal, 1])
                    money -= cost

        if core_done and seeds.get("TOMATO", 0) < TOMATO_SEED_TARGET and money > 1000:
            market_orders.append(["BUY_SEED", "TOMATO", TOMATO_SEED_TARGET - seeds.get("TOMATO", 0)])

        hires_room = max(0, 10 - len(market_orders))
        for _ in range(min(HANDS_PER_DAY, hires_room)):
            market_orders.append(["HIRE"])

    needing = []
    for s in STRUCTURES:
        sx, sy = s["pos"]
        if _structure_needs_attention(tiles[sy][sx]):
            needing.append(s)

    fx, fy = farm["farmer"]
    farmer_inv = private["inventories"][0] if private["inventories"] else {}
    if needing:
        s = needing[0]
        sx, sy = s["pos"]
        farmer_action = _keeper_action((fx, fy), tiles[sy][sx], farmer_inv, shed, s["pos"], s["shed_stop"], s["animal"], s["kind"], s["build"])
        needing = needing[1:]
    else:
        farmer_action = _idle_crop_action((fx, fy), tiles[fy][fx], seeds, farmer_inv, day, core_done)

    hands_actions = []
    hands = farm["hands"]
    for i, (hx, hy) in enumerate(hands):
        hand_inv = private["inventories"][i + 1] if i + 1 < len(private["inventories"]) else {}
        if needing:
            s = needing[0]
            sx, sy = s["pos"]
            hands_actions.append(_keeper_action((hx, hy), tiles[sy][sx], hand_inv, shed, s["pos"], s["shed_stop"], s["animal"], s["kind"], s["build"]))
            needing = needing[1:]
        else:
            hands_actions.append(_idle_crop_action((hx, hy), tiles[hy][hx], seeds, hand_inv, day, core_done))

    # Sell caps SCALE with how many animals of each type are actually
    # placed (fixed in version 3 -- flat caps caused a milk backlog once
    # cow count grew, which is what capped the version-2 sweep's mean).
    n_cow_placed = sum(1 for s in STRUCTURES if s["animal"] == "COW"
                        and isinstance(tiles[s["pos"][1]][s["pos"][0]], dict)
                        and tiles[s["pos"][1]][s["pos"][0]].get("animal") == "COW")
    n_sheep_placed = sum(1 for s in STRUCTURES if s["animal"] == "SHEEP"
                          and isinstance(tiles[s["pos"][1]][s["pos"][0]], dict)
                          and tiles[s["pos"][1]][s["pos"][0]].get("animal") == "SHEEP")
    milk_cap = max(3, n_cow_placed // 2)
    wool_cap = max(2, n_sheep_placed // 3)

    milk_amt = shed.get("MILK", 0)
    if milk_amt > 0:
        market_orders.append(["SELL", "MILK", min(milk_amt, milk_cap)])
    wool_amt = shed.get("WOOL", 0)
    if wool_amt > 0:
        market_orders.append(["SELL", "WOOL", min(wool_amt, wool_cap)])
    # EGG and FERTILIZER are glut-resistant (above_target 0.20 / 0.40 in
    # the source's MARKET_PARAMS) -- sell freely, same as TOMATO here.
    for product in ("EGG", "FERTILIZER", "TOMATO"):
        amt = shed.get(product, 0)
        if amt > 0:
            market_orders.append(["SELL", product, amt])

    return {"farmer": farmer_action, "hands": hands_actions[:HANDS_PER_DAY], "market": market_orders[:10]}


if __name__ == "__main__":
    from kaggle_environments import make

    env = make("kaggriculture", configuration={"episodeSteps": 720})
    env.run([my_agent, "random"])
    print("Agent score:", env.state[0]["reward"])
    print("Random score:", env.state[1]["reward"])