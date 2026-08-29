def _gen_structures(n_cow, n_sheep, shed_stop=(4, 4)):
    candidates = sorted(
        [(x, y) for x in range(5) for y in range(5) if (x, y) != shed_stop],
        key=lambda p: abs(p[0] - shed_stop[0]) + abs(p[1] - shed_stop[1])
    )
    structs = []
    for pos in candidates[:n_cow]:
        structs.append({"pos": pos, "animal": "COW", "build": "BUILD_PASTURE", "cost": 400, "shed_stop": shed_stop})
    for pos in candidates[n_cow:n_cow + n_sheep]:
        structs.append({"pos": pos, "animal": "SHEEP", "build": "BUILD_PASTURE", "cost": 500, "shed_stop": shed_stop})
    return structs


STRUCTURES = _gen_structures(n_cow=9, n_sheep=3)
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


def my_agent(obs):
    HANDS_PER_DAY = 12
    ANIMAL_RESERVE = 500
    WHEAT_BUY_BUFFER = 20

    player = obs["player"]
    farm = obs["farms"][player]
    tiles = farm["tiles"]
    private = obs["private"]
    shed = private["shed"]
    money = farm["money"]

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
            cost = next(s["cost"] for s in STRUCTURES if s["animal"] == animal)
            to_buy = min(1, needed - have)
            for _ in range(to_buy):
                if money > cost + ANIMAL_RESERVE:
                    market_orders.append(["BUY_ANIMAL", animal, 1])
                    money -= cost

        day = obs.get("day", 0)
        unlocked = farm.get("unlocked_quadrants", ["NW"])
        if 3 <= day <= 14 and len(market_orders) < 8:
            for quad, cost in [("NE", 1000), ("SW", 2000), ("SE", 4000)]:
                if quad not in unlocked and money > cost + ANIMAL_RESERVE and len(market_orders) < 9:
                    market_orders.append(["BUY_LAND"])
                    money -= cost
                    break

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
        farmer_action = ["PASS"]

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
            hands_actions.append(["PASS"])

    for product in ("WOOL", "MILK"):
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