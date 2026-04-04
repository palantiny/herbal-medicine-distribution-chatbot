from dataclasses import dataclass


@dataclass(frozen=True)
class ReconcileReport:
    monograph_only_names: frozenset[str]
    price_only_names: frozenset[str]
    both_names: frozenset[str]
    monograph_pairs: int
    price_herb_nodes: int


def reconcile_sets(
    monograph_names: set[str],
    price_names: set[str],
) -> ReconcileReport:
    both = monograph_names & price_names
    return ReconcileReport(
        monograph_only_names=frozenset(monograph_names - price_names),
        price_only_names=frozenset(price_names - monograph_names),
        both_names=frozenset(both),
        monograph_pairs=len(monograph_names),
        price_herb_nodes=len(price_names),
    )
