import io
from contextlib import redirect_stdout


def my_agent(obs):
    player = obs["player"]
    farm = obs["farms"][player]
    fx, fy = farm["farmer"]
    tile = farm["tiles"][fy][fx]
    seeds = obs["private"]["seeds"].get("WHEAT", 0)

    farmer_action = ["PASS"]
    market_orders = []

    # Keep a small buffer of wheat seeds, topped up at the start of each day
    if obs["hour"] == 0 and seeds < 5:
        market_orders.append(["BUY_SEED", "WHEAT", 5])

    if tile is None and seeds > 0:
        farmer_action = ["PLANT", "WHEAT"]
    elif isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == "WHEAT":
        if not tile.get("watered_today"):
            farmer_action = ["WATER"]
        elif tile.get("yield_units", 0) > 0:
            farmer_action = ["HARVEST"]

    # Sell any wheat we're holding in inventory
    wheat_inventory = obs["private"]["products"].get("WHEAT", 0)
    if wheat_inventory > 0:
        market_orders.append(["SELL", "WHEAT", wheat_inventory])

    return {"farmer": farmer_action, "hands": [], "market": market_orders}

def main():
    # kaggle_environments prints optional backend load failures (e.g., pyspiel)
    # on import; capture stdout so score output stays clean.
    with redirect_stdout(io.StringIO()):
        from kaggle_environments import make

    env = make("kaggriculture", configuration={"episodeSteps": 200})
    env.run([my_agent, "random"])
    print("Agent score:", env.state[0]["reward"])
    print("Random score:", env.state[1]["reward"])


if __name__ == "__main__":
    main()