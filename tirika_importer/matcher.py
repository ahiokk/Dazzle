from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

from .db import GoodRecord
from .models import InvoiceLine, MatchCandidate


@dataclass
class _IndexEntry:
    good_id: int
    source: str


def normalize_code(value: str) -> str:
    return value.strip().lower()


def normalize_code_alnum(value: str) -> str:
    return re.sub(r"[^0-9a-zа-я]+", "", value.strip().lower())


def build_article_variants(article: str) -> list[str]:
    raw = article.strip()
    if not raw:
        return []

    variants = [raw]
    lowered = raw.lower()
    for prefix in ("xmil-", "xzk-", "xkl-", "xgsp-", "xtrw-", "xms-"):
        if lowered.startswith(prefix):
            variants.append(raw[len(prefix) :])

    if "-" in raw:
        right = raw.split("-", 1)[1]
        if right:
            variants.append(right)
        pieces = [p for p in raw.split("-") if p]
        if len(pieces) >= 2:
            variants.append("-".join(pieces[-2:]))

    variants.append(normalize_code_alnum(raw))
    seen: set[str] = set()
    out: list[str] = []
    for item in variants:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


class GoodsMatcher:
    def __init__(self, catalog: dict[int, GoodRecord], article_match_field: str = "product_code") -> None:
        self.catalog = catalog
        self.article_match_field = _normalize_match_field(article_match_field)
        self._product_exact_index: dict[str, list[_IndexEntry]] = defaultdict(list)
        self._product_alnum_index: dict[str, list[_IndexEntry]] = defaultdict(list)
        self._cross_exact_index: dict[str, list[_IndexEntry]] = defaultdict(list)
        self._cross_alnum_index: dict[str, list[_IndexEntry]] = defaultdict(list)
        self._barcode_exact_index: dict[str, list[_IndexEntry]] = defaultdict(list)
        self._barcode_alnum_index: dict[str, list[_IndexEntry]] = defaultdict(list)
        self._norm_names: dict[int, str] = {}
        self._build_indexes()

    def _build_indexes(self) -> None:
        for good in self.catalog.values():
            if good.product_code:
                exact = normalize_code(good.product_code)
                alnum = normalize_code_alnum(good.product_code)
                if exact:
                    self._product_exact_index[exact].append(_IndexEntry(good.good_id, "product_code"))
                if alnum:
                    self._product_alnum_index[alnum].append(_IndexEntry(good.good_id, "product_code"))

            for cross in good.cross_codes:
                exact = normalize_code(cross)
                alnum = normalize_code_alnum(cross)
                if exact:
                    self._cross_exact_index[exact].append(_IndexEntry(good.good_id, "cross_code"))
                if alnum:
                    self._cross_alnum_index[alnum].append(_IndexEntry(good.good_id, "cross_code"))

            for barcode in good.barcodes:
                exact = normalize_code(barcode)
                alnum = normalize_code_alnum(barcode)
                if exact:
                    self._barcode_exact_index[exact].append(_IndexEntry(good.good_id, "barcode"))
                if alnum:
                    self._barcode_alnum_index[alnum].append(_IndexEntry(good.good_id, "barcode"))

            self._norm_names[good.good_id] = normalize_name(good.name)

    def match_lines(self, lines: list[InvoiceLine]) -> None:
        for line in lines:
            self.match_line(line)
            self._apply_forced_skip_markers(line)

    def match_line(self, line: InvoiceLine) -> None:
        line.raw_data.pop("_sell_initialized", None)
        article = line.article.strip()
        name = line.name.strip()

        # 1) Точное совпадение по выбранному главному полю.
        # Если код принадлежит одному товару, это надежное автосопоставление.
        code_candidates = self._find_exact_code_candidates(article)
        if code_candidates:
            line.candidates = code_candidates
            line.similar_articles = _format_similar_articles(code_candidates)
            if len(code_candidates) == 1:
                self._apply_candidate(line, code_candidates[0], status="exact")
                line.action = "import"
                line.warning = ""
            else:
                line.match_status = "ambiguous"
                line.match_method = "exact_code_ambiguous"
                line.warning = "Несколько товаров с таким кодом, выберите вручную."
                line.matched_good_id = None
                line.matched_name = line.name
                line.matched_product_code = line.article
                line.matched_buy_price = None
                line.existing_sell_price = None
                line.sell_price = line.price
                line.suggested_sell_price = None
                line.sell_price_diff_percent = None
                line.price_alert = False
                line.matched_tax_mode = 0
                line.action = "skip"
            return

        # 2) Фолбэк по названию.
        name_candidates = self._find_by_name(name, limit=8)
        line.candidates = name_candidates
        line.similar_articles = _format_similar_articles(name_candidates)
        if len(name_candidates) == 1 and name_candidates[0].score >= 0.85:
            self._apply_candidate(line, name_candidates[0], status="fuzzy")
            line.action = "import"
            line.warning = "Автосопоставление по названию. Проверьте перед импортом."
            return

        line.match_status = "not_found"
        line.match_method = ""
        line.matched_good_id = None
        line.matched_name = line.name
        line.matched_product_code = line.article
        line.matched_buy_price = None
        line.existing_sell_price = None
        line.sell_price = line.price
        line.suggested_sell_price = None
        line.sell_price_diff_percent = None
        line.price_alert = False
        line.matched_tax_mode = 0
        line.action = "create"
        line.warning = "Товар не найден автоматически."

    @staticmethod
    def _apply_forced_skip_markers(line: InvoiceLine) -> None:
        if not bool(line.raw_data.get("_cancelled_in_invoice", False)):
            return
        forced_warning = str(line.raw_data.get("_cancelled_warning", "") or "").strip()
        if not forced_warning:
            forced_warning = "Товар отменен"
        line.action = "skip"
        line.warning = forced_warning

    def search_goods(self, query: str, limit: int = 200) -> list[MatchCandidate]:
        q_raw = query.strip()
        q = q_raw.lower()
        if not q:
            ids = sorted(self.catalog.keys())
            return [self._candidate_from_good(self.catalog[i], "browse", 0.0) for i in ids[:limit]]

        # Keep manual search consistent with automatic matching:
        # first try the same exact/source-priority path as automatic matching.
        exact_candidates = self._find_exact_code_candidates(q_raw, limit=limit)
        if exact_candidates:
            return exact_candidates[:limit]

        items: list[tuple[float, MatchCandidate]] = []
        q_norm_name = normalize_name(query)
        q_alnum = normalize_code_alnum(query)
        prefer_code_only = _looks_like_article_query(q_raw)
        for good in self.catalog.values():
            score = 0.0
            method = "search"

            code = good.product_code.lower()
            if q in code:
                score = 1.0
                method = "search_code"
            elif q_alnum and q_alnum in normalize_code_alnum(good.product_code):
                score = 0.95
                method = "search_code_alnum"
            else:
                sec_score, sec_method = self._search_secondary_codes(good, q, q_alnum)
                if sec_score > 0:
                    score = sec_score
                    method = sec_method
                elif not prefer_code_only:
                    name_norm = self._norm_names.get(good.good_id, "")
                    if q_norm_name and q_norm_name in name_norm:
                        score = 0.9
                        method = "search_name"
                    else:
                        ratio = SequenceMatcher(None, q_norm_name, name_norm[: len(q_norm_name) * 2]).ratio()
                        if ratio >= 0.35:
                            score = ratio
                            method = "search_fuzzy"

            if score > 0:
                items.append((score, self._candidate_from_good(good, method, score)))

        items.sort(key=lambda x: x[0], reverse=True)
        return [cand for _, cand in items[:limit]]

    def _search_secondary_codes(
        self,
        good: GoodRecord,
        query: str,
        query_alnum: str,
    ) -> tuple[float, str]:
        best_score = 0.0
        best_method = ""

        for cross in good.cross_codes:
            cross_text = cross.lower()
            cross_alnum = normalize_code_alnum(cross)
            if query and query == cross_text:
                return 0.94, "search_secondary_cross_exact"
            if query_alnum and query_alnum == cross_alnum:
                return 0.93, "search_secondary_cross_alnum_exact"
            if query and query in cross_text and best_score < 0.90:
                best_score = 0.90
                best_method = "search_secondary_cross"
            if query_alnum and query_alnum in cross_alnum and best_score < 0.88:
                best_score = 0.88
                best_method = "search_secondary_cross_alnum"

        for barcode in good.barcodes:
            barcode_text = barcode.lower()
            barcode_alnum = normalize_code_alnum(barcode)
            if query and query == barcode_text:
                return 0.92, "search_secondary_barcode_exact"
            if query_alnum and query_alnum == barcode_alnum:
                return 0.91, "search_secondary_barcode_alnum_exact"
            if query and query in barcode_text and best_score < 0.86:
                best_score = 0.86
                best_method = "search_secondary_barcode"
            if query_alnum and query_alnum in barcode_alnum and best_score < 0.85:
                best_score = 0.85
                best_method = "search_secondary_barcode_alnum"

        return best_score, best_method

    def apply_manual_good(self, line: InvoiceLine, good_id: int) -> None:
        good = self.catalog.get(good_id)
        if not good:
            raise ValueError(f"Товар с good_id={good_id} не найден в каталоге.")
        line.raw_data.pop("_sell_initialized", None)
        cand = self._candidate_from_good(good, "manual", 1.0)
        self._apply_candidate(line, cand, status="manual")
        line.similar_articles = _format_similar_articles([cand])
        line.action = "import"
        line.warning = ""

    def find_exact_code_candidates(self, article: str, limit: int = 10) -> list[MatchCandidate]:
        return self._find_exact_code_candidates(article, limit=limit)

    def _find_exact_code_candidates(self, article: str, limit: int = 10) -> list[MatchCandidate]:
        for source in self._match_source_order():
            candidates = self._find_by_code_source(article, source, limit=limit)
            if candidates:
                return candidates[:limit]
        return []

    def _match_source_order(self) -> list[str]:
        if self.article_match_field == "barcode":
            return ["barcode", "product_code", "cross_code"]
        return ["product_code", "barcode", "cross_code"]

    def _find_primary_by_code(self, article: str) -> list[MatchCandidate]:
        return self._find_by_code_source(article, "product_code")

    def _find_secondary_by_code(self, article: str) -> list[MatchCandidate]:
        barcode = self._find_by_code_source(article, "barcode")
        cross = self._find_by_code_source(article, "cross_code")
        return _merge_candidates(barcode, cross, limit=10)

    def _find_by_code_source(self, article: str, source: str, limit: int = 10) -> list[MatchCandidate]:
        article_raw = article.strip()
        if not article_raw:
            return []

        bucket: dict[int, MatchCandidate] = {}
        exact_index, alnum_index = self._indexes_for_source(source)
        variants = [article_raw] if source == "product_code" else build_article_variants(article_raw)
        exact_score, alnum_score = _scores_for_source(source)

        for variant in variants:
            exact_key = normalize_code(variant)
            if exact_key:
                for entry in exact_index.get(exact_key, []):
                    good = self.catalog.get(entry.good_id)
                    if not good:
                        continue
                    cand = self._candidate_from_good(
                        good,
                        f"code_exact_{entry.source}",
                        exact_score,
                    )
                    bucket[good.good_id] = _pick_best(bucket.get(good.good_id), cand)

            alnum_key = normalize_code_alnum(variant)
            if alnum_key:
                for entry in alnum_index.get(alnum_key, []):
                    good = self.catalog.get(entry.good_id)
                    if not good:
                        continue
                    cand = self._candidate_from_good(
                        good,
                        f"code_alnum_{entry.source}",
                        alnum_score,
                    )
                    bucket[good.good_id] = _pick_best(bucket.get(good.good_id), cand)

        out = sorted(bucket.values(), key=lambda x: x.score, reverse=True)
        return out[:limit]

    def _indexes_for_source(
        self,
        source: str,
    ) -> tuple[dict[str, list[_IndexEntry]], dict[str, list[_IndexEntry]]]:
        if source == "barcode":
            return self._barcode_exact_index, self._barcode_alnum_index
        if source == "cross_code":
            return self._cross_exact_index, self._cross_alnum_index
        return self._product_exact_index, self._product_alnum_index

    def _find_by_name(self, name: str, limit: int = 8) -> list[MatchCandidate]:
        target = normalize_name(name)
        if not target:
            return []
        tokens = [t for t in target.split() if len(t) > 2]
        if not tokens:
            return []

        candidates: list[tuple[float, MatchCandidate]] = []
        for good in self.catalog.values():
            norm_name = self._norm_names.get(good.good_id, "")
            if not norm_name:
                continue

            token_hits = sum(1 for token in tokens if token in norm_name)
            if token_hits == 0:
                continue

            hit_score = token_hits / len(tokens)
            ratio = SequenceMatcher(None, target, norm_name).ratio()
            score = round((hit_score * 0.65) + (ratio * 0.35), 4)
            method = "name_fuzzy"
            if score >= 0.92:
                method = "name_high"
            candidates.append((score, self._candidate_from_good(good, method, score)))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [cand for _, cand in candidates[:limit]]

    def _apply_candidate(self, line: InvoiceLine, candidate: MatchCandidate, status: str) -> None:
        line.matched_good_id = candidate.good_id
        line.matched_product_code = candidate.product_code
        line.matched_name = candidate.name
        line.matched_buy_price = candidate.buy_price
        line.existing_sell_price = candidate.sell_price
        line.sell_price = candidate.sell_price
        good = self.catalog.get(candidate.good_id)
        line.matched_tax_mode = good.tax_mode if good else 0
        line.match_status = status
        line.match_method = candidate.match_method

    def _candidate_from_good(self, good: GoodRecord, method: str, score: float) -> MatchCandidate:
        return MatchCandidate(
            good_id=good.good_id,
            product_code=good.product_code,
            name=good.name,
            manufacturer=good.manufacturer,
            buy_price=good.buy_price,
            sell_price=good.sell_price,
            remainder=good.remainder,
            match_method=method,
            score=score,
        )


def normalize_name(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[\W_]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _looks_like_article_query(value: str) -> bool:
    text = normalize_code_alnum(value)
    if len(text) < 4:
        return False
    has_digit = any(ch.isdigit() for ch in text)
    has_alpha = any(ch.isalpha() for ch in text)
    return has_digit and (has_alpha or len(text) >= 6)


def _normalize_match_field(value: str) -> str:
    if str(value or "").strip().lower() == "barcode":
        return "barcode"
    return "product_code"


def _scores_for_source(source: str) -> tuple[float, float]:
    if source == "product_code":
        return 1.0, 0.97
    if source == "barcode":
        return 0.98, 0.95
    return 0.94, 0.90


def _pick_best(current: MatchCandidate | None, incoming: MatchCandidate) -> MatchCandidate:
    if current is None:
        return incoming
    if incoming.score > current.score:
        return incoming
    return current


def _merge_candidates(
    primary: list[MatchCandidate],
    secondary: list[MatchCandidate],
    *,
    limit: int = 10,
) -> list[MatchCandidate]:
    bucket: dict[int, MatchCandidate] = {}
    for cand in [*primary, *secondary]:
        bucket[cand.good_id] = _pick_best(bucket.get(cand.good_id), cand)
    merged = sorted(bucket.values(), key=lambda x: x.score, reverse=True)
    return merged[:limit]


def _format_similar_articles(candidates: list[MatchCandidate], limit: int = 5) -> str:
    if not candidates:
        return ""
    parts: list[str] = []
    for cand in candidates[:limit]:
        code = cand.product_code.strip() or "без кода"
        parts.append(f"{code} [{cand.good_id}]")
    return ", ".join(parts)

