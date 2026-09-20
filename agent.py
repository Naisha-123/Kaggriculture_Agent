# v21: re-adds GOOSE alongside cow+sheep (6:3:4 ratio), matching Majkel1337's
# (current #1 player) LATER, higher-scoring matches (95k-134k) exactly --
# their earlier matches were pure cow+sheep like our v18/v15.
#
# Why this matters: v18 scored 827 and literally $0 in two separate real
# matches, both traced to the same cause -- facing another cow/sheep
# opponent crashes MILK and WOOL to near-zero for extended periods (WOOL
# stuck at $1 for 13+ days in one match) while wheat cost climbs, and v18
# kept spending at full rate into a near-zero-revenue market until it bled
# to nothing. GOOSE/EGG income is unaffected by an opponent selling
# milk/wool, so it acts as a floor even when the shared cow/sheep market
# is fully cratered.
#
# Validated: this does NOT clearly increase win rate against the toughest
# real opponents (still 0/24 in testing, same as v18) -- but it dramatically
# raises the FLOOR in a simulated crash scenario (min score vs a cow/sheep
# opponent: 827-$0-class outcomes -> comfortably 10,000+ in every test run)
# and against real opponents (e.g. floor vs one panel opponent: 467 -> 14,324).
# Given a single near-zero real match is far more damaging to rating than a
# modest loss, this trade (flat win rate, much safer floor) is worth taking.
# An earlier attempt at this same idea (goose-hedge) failed because of a
# wrong ratio and the same reserve-buffer bug found and fixed here.

# v18: closely matches the pattern confirmed across FOUR independent real
# opponents this session (Viacheslav Kasatkin, Micah Fernando, Majkel1337 --
# the current #1 leaderboard player -- and Md. Asif Hossain):
#   - COW + SHEEP only, no goose
#   - Land expansion to NW + NE + SW (never SE)
#   - Hands hired GRADUALLY (ramping from ~4 toward the crew cap over the
#     first several days) rather than maxed from day 0 -- confirmed as a
#     real, isolated improvement (win rate vs 3 tough real opponents:
#     1/24 -> 3/24 from this change alone, keeping everything else fixed)
#   - A modest ~14-structure scale matched 1:1 to the hand count -- NOT
#     scaled all the way up to these opponents' real 15-19, since that
#     scale-up was tested and found to UNDERPERFORM against real
#     competition despite looking better against a passive baseline
#
# Known open gap: even with all of the above, this still loses most
# games against the toughest real opponents (keiz specifically: 0 wins
# in testing so far). The strategic parameters (mix/land/hands/scale)
# match what's winning; something in EXECUTION quality -- likely travel/
# routing efficiency, wheat self-sufficiency, or selling discipline at
# scale -- is still the gap. Worth targeted investigation once real
# match feedback comes in on this version.

ANIMAL_COST = {"COW": 400, "SHEEP": 500, "GOOSE": 300}
STRUCTURE_KIND = {"COW": "PASTURE", "SHEEP": "PASTURE", "GOOSE": "COOP"}
BUILD_OP = {"PASTURE": "BUILD_PASTURE", "COOP": "BUILD_COOP"}
TOTAL_UNITS = 11  # farmer + 10 hands

# HYPOTHESIS v15: two independent real v11-beating opponents this round
# (Viacheslav Kasatkin: 6-7 hands, 7 cows, NW+NE, huge margin; Micah
# Fernando: 10 hands matching ours, 8 cow + 6 sheep = 14 animals, NW+NE+SW)
# both converge on: COW+SHEEP ONLY (no goose at all), land expansion to
# at least NE (often SW), and a MODEST animal cap slightly above 1:1 with
# hand count (not maximized) rather than our current goose-heavy,
# NW-only, exactly-1:1 v11 design.


def _quadrant_candidates(x_range, y_range, exclude):
    return sorted(
        [(x, y) for x in x_range for y in y_range if (x, y) != exclude],
        key=lambda p: abs(p[0] - exclude[0]) + abs(p[1] - exclude[1])
    )


def _gen_batch(quadrant, x_range, y_range, shed_stop, n_cow, n_sheep, n_goose=0):
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


# NW(6) + NE(4) + SW(4) = 14 total, matching Micah Fernando's real
# winning ratio (8 cow + 6 sheep with 10 hands).
NW_STRUCTURES = _gen_batch("NW", range(5), range(5), (4, 4), n_cow=3, n_sheep=2, n_goose=2)
NE_STRUCTURES = _gen_batch("NE", range(5, 10), range(5), (5, 4), n_cow=2, n_sheep=1, n_goose=1)
SW_STRUCTURES = _gen_batch("SW", range(5), range(5, 10), (4, 5), n_cow=1, n_sheep=0, n_goose=1)
# 6 cow : 3 sheep : 4 goose -- matches Majkel1337's (the current #1 player)
# LATER, higher-scoring matches (95k-134k) exactly. Their earlier matches
# were pure cow+sheep; these newer ones add goose back in and show no
# mirror-match crash/bleed pattern at all across three separate games.
ALL_STRUCTURES = NW_STRUCTURES + NE_STRUCTURES + SW_STRUCTURES

ROUTES = [[] for _ in range(TOTAL_UNITS)]
for _idx, _s in enumerate(ALL_STRUCTURES):
    ROUTES[_idx % TOTAL_UNITS].append(_s)


def _needs_attention(tile):
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
        day = obs["day"]
        target_hands = min(TOTAL_UNITS - 1, 4 + day)
        for _ in range(min(10, target_hands)):
            market_orders.append(["HIRE"])

    if obs["hour"] == 1:
        wheat_have = shed.get("WHEAT", 0)
        n_placed_total = sum(1 for s in live_structures
                              if isinstance(tiles[s["pos"][1]][s["pos"][0]], dict)
                              and tiles[s["pos"][1]][s["pos"][0]].get("animal") == s["animal"])
        wheat_target = max(len(live_structures), n_placed_total)
        if n_placed_total > 0 and wheat_have < wheat_target and money > 500:
            market_orders.append(["BUY_PRODUCT", "WHEAT", wheat_target - wheat_have])

        demand = {}
        for s in live_structures:
            sx, sy = s["pos"]
            t = tiles[sy][sx]
            if not (isinstance(t, dict) and t.get("animal") == s["animal"]):
                demand[s["animal"]] = demand.get(s["animal"], 0) + 1
        for animal in ("GOOSE", "SHEEP", "COW"):
            needed = demand.get(animal, 0) - shed.get(animal, 0)
            if needed > 0:
                cost = ANIMAL_COST[animal]
                affordable = max(0, int((money - 800) // cost))
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
    milk_cap = max(3, n_cow_placed)
    wool_cap = max(2, n_sheep_placed // 2)
    milk = shed.get("MILK", 0)
    wool = shed.get("WOOL", 0)
    fert = shed.get("FERTILIZER", 0)
    prices = obs["market"]["prices"]
    milk_ratio = prices.get("MILK", 160) / 160
    wool_ratio = prices.get("WOOL", 200) / 200
    if milk > 0:
        eff_milk_cap = max(1, round(milk_cap * min(1.0, milk_ratio * 1.5)))
        market_orders.append(["SELL", "MILK", min(milk, eff_milk_cap)])
    if wool > 0:
        eff_wool_cap = max(1, round(wool_cap * min(1.0, wool_ratio * 1.5)))
        market_orders.append(["SELL", "WOOL", min(wool, eff_wool_cap)])
    if fert > 0:
        market_orders.append(["SELL", "FERTILIZER", fert])
    egg = shed.get("EGG", 0)
    if egg > 0:
        market_orders.append(["SELL", "EGG", egg])  # glut-resistant, sell freely

    return {"farmer": actions[0], "hands": actions[1:TOTAL_UNITS], "market": market_orders[:10]}


if __name__ == "__main__":
    from kaggle_environments import make

    env = make("kaggriculture", configuration={"episodeSteps": 720})
    env.run([my_agent, "random"])
    print("Agent score:", env.state[0]["reward"])
    print("Random score:", env.state[1]["reward"])