STRUCTURES = [
    {"pos": (5, 4), "animal": "GOOSE", "build": "BUILD_COOP", "cost": 300, "requires": "NE", "shed_stop": (5, 4)},
    {"pos": (1, 1), "animal": "COW", "build": "BUILD_PASTURE", "cost": 400, "requires": None, "shed_stop": (4, 4)},
    {"pos": (3, 1), "animal": "COW", "build": "BUILD_PASTURE", "cost": 400, "requires": None, "shed_stop": (4, 4)},
    {"pos": (7, 1), "animal": "SHEEP", "build": "BUILD_PASTURE", "cost": 500, "requires": "NE", "shed_stop": (5, 4)},
]
RESERVED = {s["pos"] for s in STRUCTURES}
SHED_TILES = {(4, 4), (5, 4), (4, 5), (5, 5)}
STRAWBERRY_START_DAY = 3  # let wheat/land/animals stabilize first — strawberry seeds are $100 each


def _crop_choice(x, y, day):
    if (x + y) % 2 == 0:
        return "WHEAT"
    return "STRAWBERRY" if day >= STRAWBERRY_START_DAY else "WHEAT"


def _unit_next_action(pos, tile, seeds, max_x, max_y, inv, shed, day, is_fresh_spawn):
    x, y = pos
    crop = _crop_choice(x, y, day)

    if is_fresh_spawn and (x, y) in SHED_TILES and inv.get("FERTILIZER", 0) == 0 and shed.get("FERTILIZER", 0) > 0:
        return ["PICKUP", "FERTILIZER", 1]

    if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") in ("WHEAT", "STRAWBERRY"):
        if inv.get("FERTILIZER", 0) > 0 and tile.get("fertilized_until_day", -1) < day:
            return ["FERTILIZE"]
        if not tile.get("watered_today"):
            return ["WATER"]
        if tile.get("yield_units", 0) > 0:
            return ["HARVEST"]

    if tile is None and (x, y) not in RESERVED and seeds.get(crop, 0) > 0:
        return ["PLANT", crop]

    if y % 2 == 0:
        if x < max_x:
            return ["EAST"]
        return ["SOUTH"] if y < max_y else ["NORTH"]
    else:
        if x > 0:
            return ["WEST"]
        return ["SOUTH"] if y < max_y else ["NORTH"]


def _structure_needs_attention(tile):
    if tile is None:
        return True
    if isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE"):
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
    x, y = pos
    if tile is None:
        step = _walk_toward(pos, target_pos)
        return step if step else [build_op]
    if isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE"):
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


def my_agent(obs):
    HANDS_PER_DAY = 7
    LAND_PRICES = [1000, 2000, 4000]
    LAND_RESERVE = 1000
    ANIMAL_RESERVE = 200  # lower bar than land — an empty pasture is a bigger relative loss than a thin cash buffer
    LAST_BUY_DAY = 15
    FIRST_BUY_DAY = 3
    WHEAT_FEED_RESERVE = 10
    STRAWBERRY_SEED_TARGET = 4

    player = obs["player"]
    farm = obs["farms"][player]
    tiles = farm["tiles"]
    private = obs["private"]
    seeds = private["seeds"]
    shed = private["shed"]
    money = farm["money"]
    day = obs["day"]
    num_units = 1 + len(farm["hands"])
    owned = set(farm["unlocked_quadrants"])

    max_x = 9 if ("NE" in owned or "SE" in owned) else 4
    max_y = 9 if ("SW" in owned or "SE" in owned) else 4

    market_orders = []
    if obs["hour"] == 0:
        seed_target = num_units + 2
        if seeds.get("WHEAT", 0) < seed_target:
            market_orders.append(["BUY_SEED", "WHEAT", seed_target - seeds.get("WHEAT", 0)])
        if day >= STRAWBERRY_START_DAY and seeds.get("STRAWBERRY", 0) < STRAWBERRY_SEED_TARGET and money > 500:
            market_orders.append(["BUY_SEED", "STRAWBERRY", STRAWBERRY_SEED_TARGET - seeds.get("STRAWBERRY", 0)])
        for _ in range(HANDS_PER_DAY):
            market_orders.append(["HIRE"])

    n_extra_owned = len(farm["unlocked_quadrants"]) - 1
    if n_extra_owned < len(LAND_PRICES) and FIRST_BUY_DAY <= day <= LAST_BUY_DAY:
        next_cost = LAND_PRICES[n_extra_owned]
        if money > next_cost + LAND_RESERVE:
            market_orders.append(["BUY_LAND"])

    demand = {}
    for s in STRUCTURES:
        if s["requires"] and s["requires"] not in owned:
            continue
        sx, sy = s["pos"]
        t = tiles[sy][sx]
        placed = isinstance(t, dict) and t.get("animal") == s["animal"]
        if not placed:
            demand[s["animal"]] = demand.get(s["animal"], 0) + 1
    for animal, needed in demand.items():
        have = shed.get(animal, 0)
        cost = next(s["cost"] for s in STRUCTURES if s["animal"] == animal)
        if have < needed and money > cost + ANIMAL_RESERVE:
            market_orders.append(["BUY_ANIMAL", animal, 1])

    fx, fy = farm["farmer"]
    farmer_inv = private["inventories"][0] if private["inventories"] else {}
    farmer_action = _unit_next_action((fx, fy), tiles[fy][fx], seeds, max_x, max_y, farmer_inv, shed, day, False)

    needing = []
    for s in STRUCTURES:
        if s["requires"] and s["requires"] not in owned:
            continue
        sx, sy = s["pos"]
        if _structure_needs_attention(tiles[sy][sx]):
            needing.append(s)

    hands_actions = []
    hands = farm["hands"]
    assigned = 0
    for i, (hx, hy) in enumerate(hands):
        hand_inv = private["inventories"][i + 1] if i + 1 < len(private["inventories"]) else {}
        if assigned < len(needing):
            s = needing[assigned]
            sx, sy = s["pos"]
            hands_actions.append(_keeper_action((hx, hy), tiles[sy][sx], hand_inv, shed, s["pos"], s["shed_stop"], s["animal"], s["build"]))
            assigned += 1
        else:
            is_fresh = obs["hour"] == 0
            hands_actions.append(_unit_next_action((hx, hy), tiles[hy][hx], seeds, max_x, max_y, hand_inv, shed, day, is_fresh))

    wheat_inventory = shed.get("WHEAT", 0)
    sellable_wheat = max(0, wheat_inventory - WHEAT_FEED_RESERVE)
    if sellable_wheat > 0:
        market_orders.append(["SELL", "WHEAT", sellable_wheat])
    for product in ("STRAWBERRY", "EGG", "MILK", "WOOL"):
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