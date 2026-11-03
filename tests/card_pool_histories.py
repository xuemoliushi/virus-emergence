"""Exhaust all candidate-availability histories, quotienting the 16 shared cards.

Rarity is deliberately ignored: this is a superset of reachable offers, so a
lower bound here also covers every weighted history and debug weight override.
The two capacity cards stay distinct, including capacity-6's prerequisite.
"""
import itertools
import json
from pathlib import Path
from lua_test_runtime import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


def verify():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute("package.path=" + repr(str(ROOT/'scripts/?.lua').replace('\\','/')) + "..';'..package.path")
    definitions = lua.eval("require('Core.Config').Cards.definitions")
    special_ids = ['swarm_capacity_4', 'swarm_capacity_6']
    cards = {card['id']: card for _, card in definitions.items()}
    assert len(cards) == 18 and len([c for id,c in cards.items() if id not in special_ids]) == 16
    for id,card in cards.items():
        if id not in special_ids:
            assert (card['minRound'] or 1) == 1 and card['prerequisites'] is None
    for i,id in enumerate(special_ids):
        assert (cards[id]['minRound'] or 1) == 1
        if i == 1:
            assert list(cards[id]['prerequisites'].values()) == ['swarm_capacity_4']
        else:
            assert cards[id]['prerequisites'] is None
    # shared acquired, previous-round unchosen, two-round-old unchosen,
    # special status (-1 acquired, 0 eligible, 1/2 remaining cooldown rounds).
    states = {(0, 0, 0, (0, 0))}
    rows = []
    for round_no in range(1, 7):
        next_states = set()
        minimum = 100
        for acquired, recent, older, special in states:
            shared = 16 - acquired - recent - older
            available = [i for i, status in enumerate(special)
                         if status == 0 and (i != 1 or special[0] == -1)]
            minimum = min(minimum, shared + len(available))
            assert shared + len(available) >= 3
            for n in range(min(3, len(available)) + 1):
                count = 3 - n
                if count > shared:
                    continue
                for offer in itertools.combinations(available, n):
                    # 2 means choose one of the exchangeable shared cards.
                    for selected in list(offer) + ([2] if count else []):
                        updated = [max(0, s - 1) if s >= 0 else -1 for s in special]
                        for card in offer:
                            updated[card] = -1 if card == selected else 2
                        next_states.add((acquired + (selected == 2),
                                         count - (selected == 2), recent,
                                         tuple(updated)))
        rows.append({'round': round_no, 'equivalence_states': len(states),
                     'minimum_eligible': minimum, 'next_states': len(next_states)})
        states = next_states
    return rows


if __name__ == '__main__':
    rows = verify()
    output = ROOT / 'validation/mechanism-cards-20261011/card-pool-histories.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print(json.dumps(rows, indent=2))
