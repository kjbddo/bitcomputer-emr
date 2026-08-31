"""테스트용 ArangoDB fake.

python-arango를 실제로 띄우지 않고 in-memory에서 collection / vector search /
graph traversal을 흉내낸다. 실제 ArangoDB 연동 테스트는 docker-compose로 별도 수행 권장.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from app.db.repositories import CaseRepository
from app.models.schemas import SimilarCase


class _FakeRepo(CaseRepository):
    def __init__(self) -> None:
        # 부모 __init__ 호출 우회(실제 db 의존). 인스턴스에서 필요한 속성만 채운다.
        self.db = None  # type: ignore
        self.settings = None  # type: ignore
        self.cases: Dict[str, Dict[str, Any]] = {}
        self.edges: Dict[str, List[Dict[str, Any]]] = {}
        self.feedback: List[Dict[str, Any]] = []

    # ---------- write ----------
    def insert_case(self, doc):
        self.cases[doc["_key"]] = dict(doc)
        return self.cases[doc["_key"]]

    def add_case_disease(self, case_key, disease_key, *, confidence=1.0, source="ground_truth"):
        self.edges.setdefault("case_has_disease", []).append({
            "_from": f"xray_cases/{case_key}",
            "_to": f"diseases/{disease_key}",
            "confidence": confidence,
            "source": source,
        })

    def add_case_finding(self, case_key, finding_key, score=0.8):
        self.edges.setdefault("case_has_finding", []).append({
            "_from": f"xray_cases/{case_key}",
            "_to": f"findings/{finding_key}",
            "score": score,
        })

    def add_case_roi_anomaly(self, case_key, roi_key, *, mean_error, p95_error, severity):
        self.edges.setdefault("case_has_roi_anomaly", []).append({
            "_from": f"xray_cases/{case_key}",
            "_to": f"rois/{roi_key}",
            "meanError": mean_error,
            "p95Error": p95_error,
            "severity": severity,
        })

    def delete_case_edges(self, case_key):
        """실제 저장소와 같은 규칙으로 이 케이스에서 나가는 간선을 지운다.

        fake 가 이것을 흉내 내지 않으면, 덮어쓰기에서 낡은 간선이 남는 결함을
        테스트가 볼 수 없다 - fake 쪽에서만 조용히 통과한다.
        """
        removed = 0
        src = f"xray_cases/{case_key}"
        for name, edges in self.edges.items():
            keep = [e for e in edges if e.get("_from") != src]
            removed += len(edges) - len(keep)
            self.edges[name] = keep
        return removed

    def reset_cases(self):
        removed = {"xray_cases": len(self.cases)}
        self.cases.clear()
        for name, edges in self.edges.items():
            removed[name] = len(edges)
        self.edges.clear()
        return removed

    # ---------- read ----------
    def get_case(self, case_key):
        return self.cases.get(case_key)

    def vector_search(
        self,
        field: str,
        embedding,
        *,
        view: Optional[str] = None,
        model_version: Optional[str] = None,
        mask_version: Optional[str] = None,
        top_k: int = 20,
    ) -> List[SimilarCase]:
        q = np.asarray(embedding, dtype=np.float32)
        qn = float(np.linalg.norm(q))
        results: List[SimilarCase] = []
        for c in self.cases.values():
            if view is not None and c.get("view") != view:
                continue
            if model_version is not None and c.get("modelVersion") != model_version:
                continue
            if mask_version is not None and c.get("maskVersion") != mask_version:
                continue
            v = c.get(field)
            if not v:
                continue
            v = np.asarray(v, dtype=np.float32)
            vn = float(np.linalg.norm(v))
            sim = float(v @ q / (vn * qn)) if (vn > 0 and qn > 0) else 0.0
            results.append(
                SimilarCase(
                    caseId=c["_key"],
                    similarity=sim,
                    diseaseTags=c.get("diseaseTags", []),
                    findingTags=c.get("findingTags", []),
                    roiStats=c.get("roiStats", {}),
                    imagePath=c.get("imagePath"),
                    heatmapPath=c.get("heatmapPath"),
                )
            )
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:top_k]

    def graph_traversal(self, case_keys):
        return []

    def add_feedback(self, case_key, payload):
        record = dict(payload)
        record["caseId"] = case_key
        self.feedback.append(record)
        return record
