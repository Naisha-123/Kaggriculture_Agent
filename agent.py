SHED_TILES = {(4, 4), (5, 4), (4, 5), (5, 5)}


def _unit_next_action(pos, tile, seeds, max_x, max_y, inv, shed, day, is_fresh_spawn):
    x, y = pos
    crop = "WHEAT" if (x + y) % 2 == 0 else "CARROT"

    # Right after spawning at a shed-adjacent tile, grab one fertilizer if
    # available — cheap, single action, no detour needed.
    if is_fresh_spawn and (x, y) in SHED_TILES and inv.get("FERTILIZER", 0) == 0 and shed.get("FERTILIZER", 0) > 0:
        return ["PICKUP", "FERTILIZER", 1]

    if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") in ("WHEAT", "CARROT"):
        # Apply fertilizer once per plant, before watering, while we're carrying one
        if inv.get("FERTILIZER", 0) > 0 and tile.get("fertilized_until_day", -1) < day:
            return ["FERTILIZE"]
        if not tile.get("watered_today"):
            return ["WATER"]
        if tile.get("yield_units", 0) > 0:
            return ["HARVEST"]

    if tile is None and seeds.get(crop, 0) > 0:
        return ["PLANT", crop]

    if y % 2 == 0:
        if x < max_x:
            return ["EAST"]
        return ["SOUTH"] if y < max_y else ["NORTH"]
    else:
        if x > 0:
            return ["WEST"]
        return ["SOUTH"] if y < max_y else ["NORTH"]


def _coop_needs_attention(coop_tile):
    if coop_tile is None:
        return True
    if isinstance(coop_tile, dict) and coop_tile.get("kind") == "COOP":
        if "animal" not in coop_tile:
            return True
        if coop_tile.get("yield_units", 0) > 0:
            return True
        if not coop_tile.get("fed_today"):
            return True
        if not coop_tile.get("cared_today"):
            return True
    return False


def _keeper_action(pos, tile, inv, shed, coop_pos):
    x, y = pos
    rx, ry = coop_pos
    if (x, y) != (rx, ry):
        if x < rx:
            return ["EAST"]
        if x > rx:
            return ["WEST"]
        if y < ry:
            return ["SOUTH"]
        return ["NORTH"]
    if tile is None:
        return ["BUILD_COOP"]
    if isinstance(tile, dict) and tile.get("kind") == "COOP":
        if "animal" not in tile:
            if inv.get("GOOSE", 0) > 0:
                return ["PLACE", "GOOSE"]
            if shed.get("GOOSE", 0) > 0:
                return ["PICKUP", "GOOSE", 1]
            return ["PASS"]
        if tile.get("yield_units", 0) > 0:
            return ["HARVEST"]
        if not tile.get("fed_today"):
            if inv.get("WHEAT", 0) > 0:
                return ["FEED"]
            if shed.get("WHEAT", 0) > 0:
                return ["PICKUP", "WHEAT", 1]
            return ["PASS"]
        if not tile.get("cared_today"):
            return ["CARE"]
        if tile.get("fertilizer_available"):
            return ["COLLECT_FERTILIZER"]
        return ["PASS"]
    return ["PASS"]


def my_agent(obs):
    HANDS_PER_DAY = 5
    LAND_PRICES = [1000, 2000, 4000]
    MONEY_RESERVE = 1000
    LAST_BUY_DAY = 15
    FIRST_BUY_DAY = 3
    COOP_POS = (5, 4)
    WHEAT_FEED_RESERVE = 4

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
        if seeds.get("CARROT", 0) < seed_target:
            market_orders.append(["BUY_SEED", "CARROT", seed_target - seeds.get("CARROT", 0)])
        for _ in range(HANDS_PER_DAY):
            market_orders.append(["HIRE"])

    n_extra_owned = len(farm["unlocked_quadrants"]) - 1
    if n_extra_owned < len(LAND_PRICES) and FIRST_BUY_DAY <= day <= LAST_BUY_DAY:
        next_cost = LAND_PRICES[n_extra_owned]
        if money > next_cost + MONEY_RESERVE:
            market_orders.append(["BUY_LAND"])

    coop_tile = tiles[COOP_POS[1]][COOP_POS[0]]
    has_goose_placed = isinstance(coop_tile, dict) and coop_tile.get("animal") == "GOOSE"
    if "NE" in owned and not has_goose_placed and shed.get("GOOSE", 0) == 0 and money > 300 + MONEY_RESERVE:
        market_orders.append(["BUY_ANIMAL", "GOOSE", 1])

    needs_attention = "NE" in owned and _coop_needs_attention(coop_tile)

    fx, fy = farm["farmer"]
    farmer_inv = private["inventories"][0] if private["inventories"] else {}
    farmer_action = _unit_next_action((fx, fy), tiles[fy][fx], seeds, max_x, max_y, farmer_inv, shed, day, False)

    hands_actions = []
    hands = farm["hands"]
    keeper_assigned = False
    for i, (hx, hy) in enumerate(hands):
        at_coop = (hx, hy) == COOP_POS
        hand_inv = private["inventories"][i + 1] if i + 1 < len(private["inventories"]) else {}
        if i == 0 and (needs_attention or at_coop) and not keeper_assigned:
            hands_actions.append(_keeper_action((hx, hy), tiles[hy][hx], hand_inv, shed, COOP_POS))
            keeper_assigned = True
        else:
            is_fresh = obs["hour"] == 0
            hands_actions.append(_unit_next_action((hx, hy), tiles[hy][hx], seeds, max_x, max_y, hand_inv, shed, day, is_fresh))

    wheat_inventory = shed.get("WHEAT", 0)
    sellable_wheat = max(0, wheat_inventory - WHEAT_FEED_RESERVE)
    if sellable_wheat > 0:
        market_orders.append(["SELL", "WHEAT", sellable_wheat])
    carrot_inventory = shed.get("CARROT", 0)
    if carrot_inventory > 0:
        market_orders.append(["SELL", "CARROT", carrot_inventory])
    egg_inventory = shed.get("EGG", 0)
    if egg_inventory > 0:
        market_orders.append(["SELL", "EGG", egg_inventory])

    return {"farmer": farmer_action, "hands": hands_actions, "market": market_orders}


if __name__ == "__main__":
    from kaggle_environments import make

    env = make("kaggriculture", configuration={"episodeSteps": 720})
    env.run([my_agent, "random"])
    print("Agent score:", env.state[0]["reward"])
    print("Random score:", env.state[1]["reward"])