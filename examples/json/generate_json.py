#!/usr/bin/env python3
"""Generate /tmp/1.json for the kostya/benchmarks JSON test."""

import json
import random

x = []
for _ in range(524288):
    h = {
        "x": random.random() * -10e-30,
        "y": random.random() * 10e30,
        "z": random.random(),
        "name": "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=6))
        + " "
        + str(random.randint(0, 9999)),
        "opts": {"1": [1, True]},
    }
    x.append(h)

with open("/tmp/1.json", "w") as f:
    json.dump({"coordinates": x, "info": "some info"}, f, indent=2)

print("Generated /tmp/1.json")
