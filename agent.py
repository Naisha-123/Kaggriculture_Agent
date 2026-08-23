def _unit_next_action(pos, tile, seeds, max_x, max_y):
    x, y = pos
    if tile is None and seeds > 0:
        return ["PLANT", "WHEAT"]
    if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == "WHEAT":
        if not tile.get("watered_today"):
            return ["WATER"]
        if tile.get("yield_units", 0) > 0:
            return ["HARVEST"]
    # Nothing to do here — sweep the owned bounding box in a boustrophedon
    # (snake) pattern so every row gets covered, alternating direction each row.
    if y % 2 == 0:
        if x < max_x:
            return ["EAST"]
        return ["SOUTH"] if y < max_y else ["NORTH"]
    else:
        if x > 0:
            return ["WEST"]
        return ["SOUTH"] if y < max_y else ["NORTH"]


def my_agent(obs):
    HANDS_PER_DAY = 3
    LAND_PRICES = [1000, 2000, 4000]
    MONEY_RESERVE = 1000
    LAST_BUY_DAY = 15
    FIRST_BUY_DAY = 3

    player = obs["player"]
    farm = obs["farms"][player]
    tiles = farm["tiles"]
    seeds = obs["private"]["seeds"].get("WHEAT", 0)
    money = farm["money"]
    day = obs["day"]
    num_units = 1 + len(farm["hands"])
    owned = set(farm["unlocked_quadrants"])

    max_x = 9 if ("NE" in owned or "SE" in owned) else 4
    max_y = 9 if ("SW" in owned or "SE" in owned) else 4

    market_orders = []
    if obs["hour"] == 0:
        seed_target = num_units + 2
        if seeds < seed_target:
            market_orders.append(["BUY_SEED", "WHEAT", seed_target - seeds])
        for _ in range(HANDS_PER_DAY):
            market_orders.append(["HIRE"])

    n_extra_owned = len(farm["unlocked_quadrants"]) - 1
    if n_extra_owned < len(LAND_PRICES) and FIRST_BUY_DAY <= day <= LAST_BUY_DAY:
        next_cost = LAND_PRICES[n_extra_owned]
        if money > next_cost + MONEY_RESERVE:
            market_orders.append(["BUY_LAND"])

    fx, fy = farm["farmer"]
    farmer_action = _unit_next_action((fx, fy), tiles[fy][fx], seeds, max_x, max_y)
    hands_actions = [_unit_next_action((hx, hy), tiles[hy][hx], seeds, max_x, max_y) for hx, hy in farm["hands"]]

    wheat_inventory = obs["private"]["shed"].get("WHEAT", 0)
    if wheat_inventory > 0:
        market_orders.append(["SELL", "WHEAT", wheat_inventory])

    return {"farmer": farmer_action, "hands": hands_actions, "market": market_orders}


if __name__ == "__main__":
    import io
    from contextlib import redirect_stdout
    with redirect_stdout(io.StringIO()):
        from kaggle_environments import make

    env = make("kaggriculture", configuration={"episodeSteps": 720})
    env.run([my_agent, "random"])
    print("Agent score:", env.state[0]["reward"])
    print("Random score:", env.state[1]["reward"])