from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# Common Chinese stamp suffix tokens — stripped before company-name comparison
# so a customer named "光明物流" still matches OCR "光明物流有限公司发票专用章".
_STAMP_NOISE_TOKENS = (
    "财务专用章",
    "发票专用章",
    "合同专用章",
    "业务专用章",
    "报关专用章",
    "公章",
    "专用章",
    "有限公司",
    "有限责任公司",
    "股份有限公司",
    "（有限公司）",
    "(有限公司)",
)


@dataclass(frozen=True)
class OcrMatchResult:
    matched: bool
    score: float           # in [0, 1]; only meaningful when matched=True
    evidence: str          # the OCR string that triggered the match
    raw_texts: list[str]


def _normalise_text(text: str) -> str:
    """Lowercase + strip whitespace + remove common stamp suffix words.

    Keeps Chinese characters as-is; removes ASCII punctuation/whitespace and
    canonical 'noise' tokens common on chops.
    """
    if not text:
        return ""
    s = text.strip().lower()
    s = re.sub(r"[\s 　]+", "", s)
    s = re.sub(r"[\.,\-_/\\:;!?~`()\[\]{}'\"]+", "", s)
    for token in _STAMP_NOISE_TOKENS:
        s = s.replace(token, "")
    return s


def _ngram_overlap(a: str, b: str, n: int = 2) -> float:
    """Character-level n-gram Jaccard overlap, clipped to [0, 1].

    Robust to OCR errors (one-char substitutions cost less than full match)
    and to extra/missing tokens (extra company-suffix gets diluted).
    """
    if not a or not b:
        return 0.0
    if len(a) < n or len(b) < n:
        return 1.0 if a == b else 0.0
    ga = {a[i : i + n] for i in range(len(a) - n + 1)}
    gb = {b[i : i + n] for i in range(len(b) - n + 1)}
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


class StampOcrMatcher:
    """OCR-based shortcut for stamp verification.

    Strategy:
      1. Run OCR on the stamp crop.
      2. Compare each detected text against the customer's registered name
         using a normalised n-gram overlap (forgiving of OCR errors and
         common stamp suffixes like "发票专用章").
      3. If overlap clears `match_threshold`, short-circuit similarity scoring
         and report a high-confidence "matched".

    Backend selection is lazy and best-effort: it tries PaddleOCR, then
    RapidOCR, then EasyOCR. If none are installed (or the chosen backend
    fails to load), the matcher reports `is_available=False` and routes
    fall back to the regular embedding pipeline. This means the OCR feature
    is opt-in via dependency installation, not a hard requirement.
    """

    BACKEND_PADDLE = "paddleocr"
    BACKEND_RAPID = "rapidocr"
    BACKEND_EASY = "easyocr"
    BACKEND_DISABLED = "disabled"

    def __init__(
        self,
        *,
        enabled: bool = True,
        match_threshold: float = 0.5,
        min_company_length: int = 2,
        languages: Iterable[str] = ("ch_sim", "en"),
    ) -> None:
        self.enabled = enabled
        self.match_threshold = match_threshold
        self.min_company_length = min_company_length
        self.languages = list(languages)

        self._backend: str = self.BACKEND_DISABLED
        self._engine = None

        if self.enabled:
            self._initialise_backend()

    @property
    def is_available(self) -> bool:
        return self.enabled and self._backend != self.BACKEND_DISABLED and self._engine is not None

    @property
    def backend(self) -> str:
        return self._backend

    # --- Public API --------------------------------------------------------

    def extract_texts(
        self,
        image_bytes: bytes,
        bbox: Iterable[float] | None = None,
    ) -> list[str]:
        if not self.is_available:
            return []
        try:
            crop = self._prepare_crop(image_bytes, bbox)
            return self._run_ocr(crop)
        except Exception as exc:
            logger.warning("OCR extraction failed, skipping: %s", exc)
            return []

    def match_company(
        self,
        texts: Iterable[str],
        customer_name: str,
    ) -> OcrMatchResult:
        normalised_target = _normalise_text(customer_name)
        raw_texts = [t for t in texts if t]

        if (
            not normalised_target
            or len(normalised_target) < self.min_company_length
            or not raw_texts
        ):
            return OcrMatchResult(matched=False, score=0.0, evidence="", raw_texts=raw_texts)

        best_score = 0.0
        best_evidence = ""

        for text in raw_texts:
            normalised = _normalise_text(text)
            if not normalised:
                continue

            # Strong substring containment (either side).
            if normalised_target in normalised or normalised in normalised_target:
                # Bias the score by how much of the target the candidate covers.
                ratio = min(1.0, len(normalised_target) / max(1, len(normalised)))
                score = max(0.92, 0.85 + 0.1 * ratio)
                if score > best_score:
                    best_score = score
                    best_evidence = text
                continue

            score = _ngram_overlap(normalised, normalised_target, n=2)
            if score > best_score:
                best_score = score
                best_evidence = text

        if best_score >= self.match_threshold:
            return OcrMatchResult(
                matched=True,
                score=min(1.0, best_score),
                evidence=best_evidence,
                raw_texts=raw_texts,
            )
        return OcrMatchResult(
            matched=False, score=best_score, evidence=best_evidence, raw_texts=raw_texts
        )

    def verify_stamp(
        self,
        *,
        image_bytes: bytes,
        bbox: Iterable[float] | None,
        customer_name: str,
    ) -> OcrMatchResult:
        texts = self.extract_texts(image_bytes, bbox)
        return self.match_company(texts, customer_name)

    # --- Internals ---------------------------------------------------------

    def _prepare_crop(
        self, image_bytes: bytes, bbox: Iterable[float] | None
    ) -> np.ndarray:
        array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("Failed to decode image bytes for OCR")

        if bbox is None:
            return image

        h, w = image.shape[:2]
        x, y, bw, bh = [int(float(v)) for v in bbox]
        # Slight padding helps OCR pick up perimeter text on stamps.
        pad = max(2, int(0.05 * max(bw, bh)))
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(w, x + bw + pad)
        y2 = min(h, y + bh + pad)
        if x2 <= x1 + 1 or y2 <= y1 + 1:
            return image
        return image[y1:y2, x1:x2]

    def _initialise_backend(self) -> None:
        # 1) PaddleOCR — best Chinese accuracy in our experience.
        try:
            from paddleocr import PaddleOCR  # type: ignore

            self._engine = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
            self._backend = self.BACKEND_PADDLE
            logger.info("StampOcrMatcher backend: PaddleOCR")
            return
        except Exception as exc:
            logger.debug("PaddleOCR unavailable: %s", exc)

        # 2) RapidOCR — lightweight ONNX runtime fallback.
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore

            self._engine = RapidOCR()
            self._backend = self.BACKEND_RAPID
            logger.info("StampOcrMatcher backend: RapidOCR")
            return
        except Exception as exc:
            logger.debug("RapidOCR unavailable: %s", exc)

        # 3) EasyOCR — last resort.
        try:
            import easyocr  # type: ignore

            mapped = []
            for lang in self.languages:
                if lang in {"ch_sim", "zh", "zh-cn"}:
                    mapped.append("ch_sim")
                elif lang in {"ch_tra", "zh-tw"}:
                    mapped.append("ch_tra")
                else:
                    mapped.append(lang)
            self._engine = easyocr.Reader(mapped, gpu=False, verbose=False)
            self._backend = self.BACKEND_EASY
            logger.info("StampOcrMatcher backend: EasyOCR")
            return
        except Exception as exc:
            logger.debug("EasyOCR unavailable: %s", exc)

        logger.info(
            "StampOcrMatcher disabled — no OCR backend installed (paddleocr | rapidocr_onnxruntime | easyocr)"
        )
        self._backend = self.BACKEND_DISABLED
        self._engine = None

    def _run_ocr(self, image: np.ndarray) -> list[str]:
        if self._engine is None:
            return []

        if self._backend == self.BACKEND_PADDLE:
            results = self._engine.ocr(image, cls=True)
            texts: list[str] = []
            for line in results or []:
                for entry in line or []:
                    try:
                        texts.append(str(entry[1][0]))
                    except (IndexError, TypeError):
                        continue
            return texts

        if self._backend == self.BACKEND_RAPID:
            result, _ = self._engine(image)
            texts = []
            for entry in result or []:
                try:
                    texts.append(str(entry[1]))
                except (IndexError, TypeError):
                    continue
            return texts

        if self._backend == self.BACKEND_EASY:
            results = self._engine.readtext(image, detail=1, paragraph=False)
            return [str(item[1]) for item in (results or [])]

        return []
