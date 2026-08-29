ANIMAL_COST = {"COW": 400, "SHEEP": 500}


def _gen_structures(n_cow, n_sheep, shed_stop=(4, 4)):
    candidates = sorted(
        [(x, y) for x in range(5) for y in range(5) if (x, y) != shed_stop],
        key=lambda p: abs(p[0] - shed_stop[0]) + abs(p[1] - shed_stop[1])
    )
    structs = []
    i = 0
    for animal, n in (("COW", n_cow), ("SHEEP", n_sheep)):
        for _ in range(n):
            structs.append({"pos": candidates[i], "animal": animal, "build": "BUILD_PASTURE", "cost": ANIMAL_COST[animal], "shed_stop": shed_stop})
            i += 1
    return structs


STRUCTURES = _gen_structures(n_cow=7, n_sheep=2)
RESERVED = {s["pos"] for s in STRUCTURES}


def _structure_needs_attention(tile):
    if tile is None:
        return True
    if isinstance(tile, dict) and tile.get("kind") == "PASTURE":
        if "animal" not in tile:
            return True
        if tile.get("yield_units", 0) > 0:
            return True
        if not tile.get("fed_today"):
            return True
        if not tile.get("cared_today"):
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


def _keeper_action(pos, tile, inv, shed, target_pos, shed_stop, animal, build_op):
    if tile is None:
        step = _walk_toward(pos, target_pos)
        return step if step else [build_op]
    if isinstance(tile, dict) and tile.get("kind") == "PASTURE":
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
    HANDS_PER_DAY = 12
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
        farmer_action = _keeper_action((fx, fy), tiles[sy][sx], farmer_inv, shed, s["pos"], s["shed_stop"], s["animal"], s["build"])
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
            hands_actions.append(_keeper_action((hx, hy), tiles[sy][sx], hand_inv, shed, s["pos"], s["shed_stop"], s["animal"], s["build"]))
            needing = needing[1:]
        else:
            hands_actions.append(_idle_crop_action((hx, hy), tiles[hy][hx], seeds, hand_inv, day, core_done))

    for product in ("WOOL", "MILK", "TOMATO"):
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