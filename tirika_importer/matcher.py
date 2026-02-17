from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

from .db import GoodRecord
from .models import InvoiceLine, MatchCandidate


@dataclass(slots=True)
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
    def __init__(self, catalog: dict[int, GoodRecord]) -> None:
        self.catalog = catalog
        self._product_exact_index: dict[str, list[_IndexEntry]] = defaultdict(list)
        self._product_alnum_index: dict[str, list[_IndexEntry]] = defaultdict(list)
        self._secondary_exact_index: dict[str, list[_IndexEntry]] = defaultdict(list)
        self._secondary_alnum_index: dict[str, list[_IndexEntry]] = defaultdict(list)
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
                    self._secondary_exact_index[exact].append(_IndexEntry(good.good_id, "cross_code"))
                if alnum:
                    self._secondary_alnum_index[alnum].append(_IndexEntry(good.good_id, "cross_code"))

            for barcode in good.barcodes:
                exact = normalize_code(barcode)
                alnum = normalize_code_alnum(barcode)
                if exact:
                    self._secondary_exact_index[exact].append(_IndexEntry(good.good_id, "barcode"))
                if alnum:
                    self._secondary_alnum_index[alnum].append(_IndexEntry(good.good_id, "barcode"))

            self._norm_names[good.good_id] = normalize_name(good.name)

    def match_lines(self, lines: list[InvoiceLine]) -> None:
        for line in lines:
            self.match_line(line)

    def match_line(self, line: InvoiceLine) -> None:
        line.raw_data.pop("_sell_initialized", None)
        article = line.article.strip()
        name = line.name.strip()

        # 1) Автосопоставление только по главному артикулу товара (goods.product_code).
        main_code_candidates = self._find_primary_by_code(article)
        if main_code_candidates:
            line.candidates = main_code_candidates
            line.similar_articles = _format_similar_articles(main_code_candidates)
            if len(main_code_candidates) == 1:
                self._apply_candidate(line, main_code_candidates[0], status="exact")
                line.action = "import"
                line.warning = ""
            else:
                secondary_candidates = self._find_secondary_by_code(article)
                merged = _merge_candidates(main_code_candidates, secondary_candidates, limit=10)
                line.candidates = merged
                line.similar_articles = _format_similar_articles(merged)
                line.match_status = "ambiguous"
                line.match_method = "product_code_ambiguous"
                line.warning = "Несколько товаров по главному артикулу, выберите вручную."
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

        # 2) Если точного совпадения по главному коду нет, показываем похожие из cross_codes/barcodes.
        secondary_code_candidates = self._find_secondary_by_code(article)
        if secondary_code_candidates:
            line.candidates = secondary_code_candidates
            line.similar_articles = _format_similar_articles(secondary_code_candidates)
            line.match_status = "ambiguous"
            line.match_method = "secondary_code_hint"
            line.warning = "Точный основной артикул не найден. Есть похожие по кросс-кодам/штрихкоду."
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

        # 3) Фолбэк по названию.
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

    def search_goods(self, query: str, limit: int = 200) -> list[MatchCandidate]:
        q = query.strip().lower()
        if not q:
            ids = sorted(self.catalog.keys())
            return [self._candidate_from_good(self.catalog[i], "browse", 0.0) for i in ids[:limit]]

        items: list[tuple[float, MatchCandidate]] = []
        q_norm_name = normalize_name(query)
        q_alnum = normalize_code_alnum(query)
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

    def _find_primary_by_code(self, article: str) -> list[MatchCandidate]:
        article_raw = article.strip()
        if not article_raw:
            return []

        bucket: dict[int, MatchCandidate] = {}
        exact_key = normalize_code(article_raw)
        if exact_key:
            for entry in self._product_exact_index.get(exact_key, []):
                good = self.catalog.get(entry.good_id)
                if not good:
                    continue
                score = 1.0
                cand = self._candidate_from_good(good, f"code_exact_{entry.source}", score)
                bucket[good.good_id] = _pick_best(bucket.get(good.good_id), cand)

        alnum_key = normalize_code_alnum(article_raw)
        if alnum_key:
            for entry in self._product_alnum_index.get(alnum_key, []):
                good = self.catalog.get(entry.good_id)
                if not good:
                    continue
                score = 0.97
                cand = self._candidate_from_good(good, f"code_alnum_{entry.source}", score)
                bucket[good.good_id] = _pick_best(bucket.get(good.good_id), cand)

        out = sorted(bucket.values(), key=lambda x: x.score, reverse=True)
        return out[:10]

    def _find_secondary_by_code(self, article: str) -> list[MatchCandidate]:
        variants = build_article_variants(article)
        if not variants:
            return []

        bucket: dict[int, MatchCandidate] = {}
        for variant in variants:
            exact_key = normalize_code(variant)
            if exact_key:
                for entry in self._secondary_exact_index.get(exact_key, []):
                    good = self.catalog.get(entry.good_id)
                    if not good:
                        continue
                    score = 0.94 if entry.source == "cross_code" else 0.92
                    cand = self._candidate_from_good(good, f"secondary_exact_{entry.source}", score)
                    bucket[good.good_id] = _pick_best(bucket.get(good.good_id), cand)

            alnum_key = normalize_code_alnum(variant)
            if alnum_key:
                for entry in self._secondary_alnum_index.get(alnum_key, []):
                    good = self.catalog.get(entry.good_id)
                    if not good:
                        continue
                    score = 0.9 if entry.source == "cross_code" else 0.88
                    cand = self._candidate_from_good(good, f"secondary_alnum_{entry.source}", score)
                    bucket[good.good_id] = _pick_best(bucket.get(good.good_id), cand)

        out = sorted(bucket.values(), key=lambda x: x.score, reverse=True)
        return out[:10]

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
