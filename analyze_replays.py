import json
import os
from collections import defaultdict, Counter

replay_dir = r"c:\Users\Admin\Desktop\Kaggriculture_Agent\replays"

def analyze_replay(filepath):
    """Extract key insights from a single replay."""
    with open(filepath) as f:
        data = json.load(f)
    
    rewards = data['rewards']
    agents = [a['Name'] for a in data['info']['Agents']]
    winner_idx = 0 if rewards[0] > rewards[1] else 1
    winner_name = agents[winner_idx]
    winner_reward = rewards[winner_idx]
    loser_reward = rewards[1 - winner_idx]
    
    steps = data['steps']
    
    # Track actions by the winner
    winner_actions = defaultdict(int)
    winner_market_actions = defaultdict(int)
    crops_planted = Counter()
    animals_hired = Counter()
    land_bought = 0
    hands_hired = 0
    fertilizer_used = 0
    
    for step_idx, step in enumerate(steps):
        if step_idx >= len(step):
            continue
        observation = step[winner_idx] if winner_idx < len(step) else None
        if not observation or 'observation' not in observation:
            continue
        
        obs = observation.get('observation', {})
        action = observation.get('action', {}) if 'action' in observation else {}
        
        # Parse farmer actions
        if 'farmer' in action:
            farmer_act = action['farmer']
            if isinstance(farmer_act, list) and len(farmer_act) > 0:
                main_action = farmer_act[0]
                winner_actions[main_action] += 1
                
                # Track specific crops
                if main_action == "PLANT" and len(farmer_act) > 1:
                    crops_planted[farmer_act[1]] += 1
                elif main_action == "FERTILIZE":
                    fertilizer_used += 1
        
        # Parse market actions
        if 'market' in action:
            for market_act in action.get('market', []):
                if isinstance(market_act, list) and len(market_act) > 0:
                    act_type = market_act[0]
                    winner_market_actions[act_type] += 1
                    
                    if act_type == "BUY_ANIMAL" and len(market_act) > 1:
                        animals_hired[market_act[1]] += 1
                    elif act_type == "HIRE":
                        hands_hired += 1
                    elif act_type == "BUY_LAND":
                        land_bought += 1
    
    return {
        'file': os.path.basename(filepath),
        'winner': winner_name,
        'winner_reward': winner_reward,
        'loser_reward': loser_reward,
        'margin': winner_reward - loser_reward,
        'farmer_actions': dict(winner_actions),
        'market_actions': dict(winner_market_actions),
        'crops_planted': dict(crops_planted),
        'animals_hired': dict(animals_hired),
        'fertilizer_used': fertilizer_used,
        'hands_hired': hands_hired,
        'land_bought': land_bought,
    }

# Analyze all replays
print("=" * 70)
print("KAGGRICULTURE REPLAY ANALYSIS")
print("=" * 70)

all_results = []
for fname in sorted(os.listdir(replay_dir)):
    if fname.endswith('.json'):
        fpath = os.path.join(replay_dir, fname)
        result = analyze_replay(fpath)
        all_results.append(result)
        
        print(f"\n📊 {result['file']}")
        print(f"  Winner: {result['winner']} (${result['winner_reward']:.0f}) vs ${result['loser_reward']:.0f} [+${result['margin']:.0f}]")
        
        if result['crops_planted']:
            print(f"  Crops planted: {dict(sorted(result['crops_planted'].items(), key=lambda x: -x[1]))}")
        if result['animals_hired']:
            print(f"  Animals: {dict(sorted(result['animals_hired'].items(), key=lambda x: -x[1]))}")
        if result['fertilizer_used']:
            print(f"  Fertilizer applications: {result['fertilizer_used']}")
        if result['hands_hired']:
            print(f"  Farm hands hired: {result['hands_hired']}")
        if result['land_bought']:
            print(f"  Land quadrants bought: {result['land_bought']}")

# Summary statistics
print("\n" + "=" * 70)
print("AGGREGATE PATTERNS (Top Winning Strategies)")
print("=" * 70)

avg_reward = sum(r['winner_reward'] for r in all_results) / len(all_results)
print(f"\n✓ Average winning score: ${avg_reward:.0f}")

all_crops = Counter()
all_animals = Counter()
total_fertilizer = 0
total_hands = 0
total_land = 0

for result in all_results:
    for crop, count in result['crops_planted'].items():
        all_crops[crop] += count
    for animal, count in result['animals_hired'].items():
        all_animals[animal] += count
    total_fertilizer += result['fertilizer_used']
    total_hands += result['hands_hired']
    total_land += result['land_bought']

print(f"\n🌾 Most planted crops: {all_crops.most_common()}")
print(f"🐔 Most raised animals: {all_animals.most_common()}")
print(f"✨ Total fertilizer uses: {total_fertilizer} (avg per game: {total_fertilizer/len(all_results):.1f})")
print(f"👥 Total farm hands hired: {total_hands} (avg per game: {total_hands/len(all_results):.1f})")
print(f"🏠 Total land expansions: {total_land} (avg per game: {total_land/len(all_results):.1f})")

# Profitability insights
print("\n" + "=" * 70)
print("KEY INSIGHTS FOR HIGHER PROFIT")
print("=" * 70)

if all_crops['WHEAT'] > 0:
    print(f"✓ Wheat is fundamental: {all_crops['WHEAT']} plantings across winners")
if all_crops['MELON'] > 0 or all_crops['STRAWBERRY'] > 0:
    print(f"✓ High-value crops matter: {all_crops['MELON']} melons + {all_crops['STRAWBERRY']} strawberries")
if all_animals:
    print(f"✓ Animals generate recurring revenue: {dict(all_animals.most_common(3))}")
if total_fertilizer > len(all_results) * 5:
    print(f"✓ Fertilizer is heavily used ({total_fertilizer/len(all_results):.1f} avg) → focus on high-margin crops")
if total_hands > len(all_results) * 5:
    print(f"✓ Farm hands enable parallelization → hire strategically")
if total_land > 0:
    print(f"✓ Land expansion is key to scaling → budget for quadrant purchases")
