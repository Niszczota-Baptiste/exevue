"""Calculateur de stacks Minecraft (logique pure, testable)."""


def compute(total: int, stack_size: int = 64, chest_slots: int = 27) -> dict:
    """N -> stacks de `stack_size` + reste, et conversion en coffres."""
    total = max(0, int(total))
    stack_size = max(1, int(stack_size))
    chest_slots = max(1, int(chest_slots))

    stacks = total // stack_size
    remainder = total % stack_size

    full_chests = stacks // chest_slots
    leftover_stacks = stacks % chest_slots

    return {
        "total": total,
        "stack_size": stack_size,
        "stacks": stacks,
        "remainder": remainder,
        "chest_slots": chest_slots,
        "full_chests": full_chests,
        "leftover_stacks": leftover_stacks,
    }


def describe(total: int, stack_size: int = 64, chest_slots: int = 27) -> str:
    r = compute(total, stack_size, chest_slots)
    txt = f"{r['total']} = {r['stacks']} stack(s) de {r['stack_size']} + {r['remainder']}"
    txt += (f"\n÷ coffre ({r['chest_slots']} slots) : {r['full_chests']} coffre(s) "
            f"plein(s) + {r['leftover_stacks']} stack(s)")
    return txt
