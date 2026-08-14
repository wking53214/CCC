"""Road Sign observation layer."""

from __future__ import annotations

from dataclasses import replace

from .models import Actor, RoadSign, RoadSignCategory, new_id


class RoadSignManager:
    def __init__(self, store, audit, rules) -> None:
        self.store = store
        self.audit = audit
        self.rules = rules

    def detect_road_sign(
        self,
        *,
        observation: str,
        category: RoadSignCategory,
        source_material: tuple[str, ...] = (),
        actor: Actor,
        confidence: float | None = None,
        metadata: dict | None = None,
    ) -> RoadSign:
        self.rules.evaluate(
            "CCC-ROADSIGN-001",
            bool(observation.strip()),
            reason="road signs record observations, not conclusions",
            evidence=source_material,
        )
        sign = RoadSign(
            road_sign_id=new_id("sign"),
            category=category,
            observation=observation,
            source_material=tuple(source_material),
            detected_by=actor,
            confidence=confidence,
            metadata=metadata or {},
            is_conclusion=False,
        )
        self.store.add_road_sign(sign)
        self.audit.record(
            actor=actor,
            operation="DETECT_ROAD_SIGN",
            object_id=sign.road_sign_id,
            previous_state=None,
            new_state={"category": category.value, "is_conclusion": False},
            reason="observable indicator recorded for examination",
            evidence=source_material,
            constitutional_rule="CCC-ROADSIGN-001",
        )
        return sign

    def record_road_sign(self, **kwargs) -> RoadSign:
        return self.detect_road_sign(**kwargs)

    def link_road_sign(self, road_sign_id: str, target_id: str, *, actor: Actor, reason: str) -> RoadSign:
        sign = self.store.road_signs[road_sign_id]
        updated = replace(sign, linked_ids=tuple(dict.fromkeys((*sign.linked_ids, target_id))))
        self.store.replace_road_sign(updated)
        self.audit.record(
            actor=actor,
            operation="LINK_ROAD_SIGN",
            object_id=road_sign_id,
            previous_state={"linked_ids": list(sign.linked_ids)},
            new_state={"linked_ids": list(updated.linked_ids)},
            reason=reason,
            constitutional_rule="CCC-ROADSIGN-001",
        )
        return updated

    def query_road_signs(
        self,
        *,
        category: RoadSignCategory | None = None,
        source_material: str | None = None,
        linked_id: str | None = None,
    ) -> tuple[RoadSign, ...]:
        result = tuple(self.store.road_signs.values())
        if category is not None:
            result = tuple(sign for sign in result if sign.category is category)
        if source_material is not None:
            result = tuple(sign for sign in result if source_material in sign.source_material)
        if linked_id is not None:
            result = tuple(sign for sign in result if linked_id in sign.linked_ids)
        return result
