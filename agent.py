ANIMAL_COST = {"COW": 400, "SHEEP": 500, "GOOSE": 300}
STRUCTURE_KIND = {"COW": "PASTURE", "SHEEP": "PASTURE", "GOOSE": "COOP"}
BUILD_OP = {"PASTURE": "BUILD_PASTURE", "COOP": "BUILD_COOP"}
TOTAL_UNITS = 11  # farmer + 10 hands -- deliberately fits INSIDE the game
                  # engine's real per-turn order cap (maxMarketOrdersPerTurn=10).
                  #
                  # IMPORTANT LESSON FROM v4's REAL REPLAYS (this is why this
                  # number is 11, not 15):
                  # The engine truncates ANY order list to 10 BEFORE our code's
                  # own logic even runs (`queues.append(q[:max_orders])` in the
                  # source). Requesting 14 HIRE orders in one turn silently
                  # became 10 every day in all 10 real v4 matches (hands frozen
                  # at exactly 10 always) -- that looked like a bug to fix.
                  # But actually hiring the FULL 14 (by splitting the request
                  # across two turns) makes things WORSE: hires #11-14 cost
                  # fib(10)+fib(11)+fib(12)+fib(13) = 843 of the 986 total daily
                  # cost, paid from day 0 when money is only in the hundreds --
                  # confirmed empirically to crash the economy to exactly $0 by
                  # day 11 in every trial once genuinely tested. The engine's
                  # accidental 10-hand cap was propping up every earlier
                  # version's success without us realizing it. This version
                  # hires exactly 10 on purpose, in a single turn, with no
                  # risk of ever trying (and paying for) the fatal 11th-14th
                  # hire.


def _quadrant_candidates(x_range, y_range, exclude):
    return sorted(
        [(x, y) for x in x_range for y in y_range if (x, y) != exclude],
        key=lambda p: abs(p[0] - exclude[0]) + abs(p[1] - exclude[1])
    )


def _gen_batch(quadrant, x_range, y_range, shed_stop, n_cow, n_sheep, n_goose):
    candidates = _quadrant_candidates(x_range, y_range, shed_stop)
    structs = []
    i = 0
    for animal, n in (("COW", n_cow), ("SHEEP", n_sheep), ("GOOSE", n_goose)):
        kind = STRUCTURE_KIND[animal]
        for _ in range(n):
            structs.append({
                "pos": candidates[i], "animal": animal, "kind": kind,
                "build": BUILD_OP[kind], "cost": ANIMAL_COST[animal],
                "shed_stop": shed_stop, "quadrant": quadrant,
            })
            i += 1
    return structs


# Structure count (25 total) sized to match what a SAFE 10-hand crew can
# actually attend -- testing showed 15/20/25 total structures score
# statistically the same at 11 units (crew is the bottleneck, not land),
# so the modest NW+NE+SW footprint is kept since real opponents in the
# replay pool do use expanded land.
ALL_STRUCTURES = (
    _gen_batch("NW", range(5), range(5), (4, 4), n_cow=4, n_sheep=3, n_goose=8)
    + _gen_batch("NE", range(5, 10), range(5), (5, 4), n_cow=2, n_sheep=1, n_goose=2)
    + _gen_batch("SW", range(5), range(5, 10), (4, 5), n_cow=2, n_sheep=1, n_goose=2)
)

ROUTES = [[] for _ in range(TOTAL_UNITS)]
for _idx, _s in enumerate(ALL_STRUCTURES):
    ROUTES[_idx % TOTAL_UNITS].append(_s)


def _needs_attention(tile):
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


def my_agent(obs):
    player = obs["player"]
    farm = obs["farms"][player]
    tiles = farm["tiles"]
    private = obs["private"]
    shed = private["shed"]
    money = farm["money"]
    unlocked = set(farm["unlocked_quadrants"])

    live_structures = [s for s in ALL_STRUCTURES if s["quadrant"] in unlocked]

    market_orders = []
    if obs["hour"] == 0:
        # Exactly 10 hires, exactly once -- inside the engine's real cap,
        # never split across turns (splitting is what caused the $0 crash).
        for _ in range(min(10, TOTAL_UNITS - 1)):
            market_orders.append(["HIRE"])

    if obs["hour"] == 1:
        wheat_have = shed.get("WHEAT", 0)
        n_placed_total = sum(1 for s in live_structures
                              if isinstance(tiles[s["pos"][1]][s["pos"][0]], dict)
                              and tiles[s["pos"][1]][s["pos"][0]].get("animal") == s["animal"])
        wheat_target = max(20, n_placed_total)
        if wheat_have < wheat_target and money > 500:
            market_orders.append(["BUY_PRODUCT", "WHEAT", wheat_target - wheat_have])

        # FIX vs v4: buy the FULL remaining need per animal type in one
        # order (BUY_ANIMAL takes a quantity and costs a flat per-unit
        # price, not the market curve) instead of always just 1/day --
        # the old code would have taken 10+ days to fully stock missing
        # goose alone.
        demand = {}
        for s in live_structures:
            sx, sy = s["pos"]
            t = tiles[sy][sx]
            if not (isinstance(t, dict) and t.get("animal") == s["animal"]):
                demand[s["animal"]] = demand.get(s["animal"], 0) + 1
        for animal in ("COW", "SHEEP", "GOOSE"):
            needed = demand.get(animal, 0) - shed.get(animal, 0)
            if needed > 0:
                cost = ANIMAL_COST[animal]
                affordable = max(0, int((money - 500) // cost))
                to_buy = min(needed, affordable)
                if to_buy > 0:
                    market_orders.append(["BUY_ANIMAL", animal, to_buy])
                    money -= cost * to_buy

    if obs["hour"] == 2:
        if "NE" not in unlocked and money > 1000 + 800:
            market_orders.append(["BUY_LAND"])
        elif "SW" not in unlocked and "NE" in unlocked and money > 2000 + 1500:
            market_orders.append(["BUY_LAND"])

    fx, fy = farm["farmer"]
    all_pos = [(fx, fy)] + [tuple(h) for h in farm["hands"]]
    actions = []
    for unit_idx, pos in enumerate(all_pos):
        route = [s for s in ROUTES[unit_idx] if s["quadrant"] in unlocked] if unit_idx < TOTAL_UNITS else []
        target_s = None
        for s in route:
            if _needs_attention(tiles[s["pos"][1]][s["pos"][0]]):
                target_s = s
                break
        if target_s is None:
            actions.append(["PASS"])
            continue
        inv = private["inventories"][unit_idx] if unit_idx < len(private["inventories"]) else {}
        sx, sy = target_s["pos"]
        actions.append(_keeper_action(pos, tiles[sy][sx], inv, shed, target_s["pos"],
                                       target_s["shed_stop"], target_s["animal"],
                                       target_s["kind"], target_s["build"]))

    n_cow_placed = sum(1 for s in live_structures if s["animal"] == "COW"
                        and isinstance(tiles[s["pos"][1]][s["pos"][0]], dict)
                        and tiles[s["pos"][1]][s["pos"][0]].get("animal") == "COW")
    n_sheep_placed = sum(1 for s in live_structures if s["animal"] == "SHEEP"
                          and isinstance(tiles[s["pos"][1]][s["pos"][0]], dict)
                          and tiles[s["pos"][1]][s["pos"][0]].get("animal") == "SHEEP")
    milk_cap = max(3, n_cow_placed // 2)
    wool_cap = max(2, n_sheep_placed // 3)

    milk = shed.get("MILK", 0)
    wool = shed.get("WOOL", 0)
    egg = shed.get("EGG", 0)
    fert = shed.get("FERTILIZER", 0)
    if milk > 0:
        market_orders.append(["SELL", "MILK", min(milk, milk_cap)])
    if wool > 0:
        market_orders.append(["SELL", "WOOL", min(wool, wool_cap)])
    if egg > 0:
        market_orders.append(["SELL", "EGG", egg])
    if fert > 0:
        market_orders.append(["SELL", "FERTILIZER", fert])

    return {"farmer": actions[0], "hands": actions[1:TOTAL_UNITS], "market": market_orders[:10]}


if __name__ == "__main__":
    from kaggle_environments import make

    env = make("kaggriculture", configuration={"episodeSteps": 720})
    env.run([my_agent, "random"])
    print("Agent score:", env.state[0]["reward"])
    print("Random score:", env.state[1]["reward"])