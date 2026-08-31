"""ID 생성 유틸. case_key 형식: case_<8hex>."""
from __future__ import annotations

import hashlib
import secrets


def new_case_key() -> str:
    return f"case_{secrets.token_hex(4)}"


def case_key_for_source(source_id: str) -> str:
    """같은 원본에는 언제나 같은 키를 준다.

    적재 스크립트가 재실행을 덮어쓰기로 만들기 위해 쓴다. 무작위 키를 쓰면
    같은 영상이 실행할 때마다 새 케이스가 되어 코퍼스가 통째로 복제되는데,
    각 실행이 이미지를 새 경로에 복사하므로 imagePath 로 묶어 세도 중복이
    드러나지 않는다. 실제로 202장짜리 split 이 573건이 된 적이 있다.

    `source_id` 는 원본을 유일하게 식별하는 문자열이다(예: 데이터셋 안의
    상대 경로). 해시를 쓰는 이유는 경로에 ArangoDB `_key` 가 허용하지 않는
    문자가 섞이고 길이 제한(254자)도 있기 때문이다. 앞 8바이트만 쓰는 것은
    기존 `new_case_key` 와 같은 폭을 유지하기 위해서다 - 이 규모(수십만 건)
    에서 충돌 확률은 무시할 수 있다.
    """
    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()
    return f"case_{digest[:16]}"


def safe_doc_key(name: str) -> str:
    """ArangoDB _key 허용 문자(영문, 숫자, _-:.@)만 남기고 정리."""
    return "".join(c for c in name if c.isalnum() or c in "_-.:@") or "_unknown"
