import json
import os

def diagnose_game(filepath, player_to_analyze=1):
    """Deep-dive into a specific game to identify decision failures."""
    with open(filepath) as f:
        data = json.load(f)
    
    steps = data['steps']
    agents = [a['Name'] for a in data['info']['Agents']]
    
    # Track key metrics at key times
    print(f"\n{'='*80}")
    print(f"Game: {os.path.basename(filepath)}")
    print(f"Player {player_to_analyze}: {agents[player_to_analyze]}")
    print(f"Opponent: {agents[1-player_to_analyze]}")
    print(f"{'='*80}")
    
    # Sample key days: start, middle, end
    check_days = [0, 7, 14, 20, 29]
    
    for day in check_days:
        step_idx = min(day * 24, len(steps) - 1)
        if step_idx >= len(steps):
            break
            
        step = steps[step_idx]
        if player_to_analyze >= len(step):
            continue
            
        obs = step[player_to_analyze].get('observation', {})
        if not obs:
            continue
        
        farms = obs.get('farms', [])
        if player_to_analyze >= len(farms):
            continue
        
        farm = farms[player_to_analyze]
        private = obs.get('private', {})
        
        money = farm.get('money', 0)
        hands = len(farm.get('hands', []))
        shed = private.get('shed', {})
        
        # Count animals
        animals = 0
        tiles = farm.get('tiles', [])
        for row in tiles:
            for tile in row:
                if isinstance(tile, dict) and tile.get('kind') in ['COOP', 'PASTURE']:
                    if tile.get('animal'):
                        animals += 1
        
        wheat = shed.get('WHEAT', 0)
        products = sum(private.get('products', {}).values())
        
        print(f"\nDay {day:2d}:")
        print(f"  Money: ${money:>7.0f}")
        print(f"  Hands: {hands}")
        print(f"  Animals: {animals}")
        print(f"  Wheat in shed: {wheat}")
        print(f"  Products in shed: {products}")
        
        # Check opponent's state
        opp = farms[1-player_to_analyze]
        opp_money = opp.get('money', 0)
        opp_animals = 0
        for row in opp.get('tiles', []):
            for tile in row:
                if isinstance(tile, dict) and tile.get('kind') in ['COOP', 'PASTURE']:
                    if tile.get('animal'):
                        opp_animals += 1
        print(f"  Opponent: ${opp_money:>7.0f}, {opp_animals} animals")

# Analyze the worst performing game
print("DIAGNOSING WORST PERFORMANCE: Game 7")
print("Your agent score: $10,925 vs opponent $23,187")
diagnose_game(r"c:\Users\Admin\Desktop\Kaggriculture_Agent\replays\Version1\102458048.json", player_to_analyze=1)

print("\n" + "="*80)
print("DIAGNOSING BEST PERFORMANCE: Game 3")
print("Your agent score: $40,189 vs opponent $15,465")
diagnose_game(r"c:\Users\Admin\Desktop\Kaggriculture_Agent\replays\Version1\102449020.json", player_to_analyze=0)

print("\n" + "="*80)
print("DIAGNOSING CLOSE LOSS: Game 4")
print("Your agent score: $48,592 vs opponent $71,073")
diagnose_game(r"c:\Users\Admin\Desktop\Kaggriculture_Agent\replays\Version1\102451260.json", player_to_analyze=0)
