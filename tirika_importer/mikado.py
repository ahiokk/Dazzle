"""SOAP-клиент веб-сервиса «Микадо» (mikado-parts.ru/ws1).

Безопасность: API Микадо НЕ умеет отправлять/оформлять заказ — только проценка
(Code_Search / Code_Info) и добавление позиций в КОРЗИНУ (Basket_Add). Финальное
оформление заказа делает человек в личном кабинете Микадо. Поэтому здесь намеренно
НЕТ метода «оформить/отправить заказ».

Авторизация: каждый вызов принимает ClientID (код клиента) + Password. Дополнительно
Микадо требует привязку IP (см. кабинет, метод Get_MyIP).
"""
from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "https://mikado-parts.ru/ws1/"
SERVICE_NS = "http://mikado-parts.ru/service"
BASKET_NS = "http://mikado-parts.ru/ws1/"
DEFAULT_NOTE = "Dazzle"


class MikadoError(RuntimeError):
    pass


@dataclass
class MikadoOffer:
    zakaz_code: str
    brand: str
    name: str
    supplier: str = ""
    country: str = ""
    producer_code: str = ""
    price_rur: float = 0.0
    on_stocks: str = ""
    srok: str = ""
    code_type: str = ""
    min_qty: str = ""


@dataclass
class MikadoPrice:
    price_rur: float = 0.0
    currency: str = ""
    on_stocks: str = ""
    srok: str = ""
    srok_max: str = ""
    comment: str = ""
    delivery_type: str = ""
    rating: int = 0


@dataclass
class BasketLine:
    id: int = 0
    zakaz_code: str = ""
    name: str = ""
    qty: float = 0.0
    price_rur: float = 0.0
    status: str = ""
    srok: str = ""
    notes: str = ""


@dataclass
class BasketAddResult:
    message: str = ""
    id: int = 0
    ordered_qty: int = 0
    ordered_code: str = ""


# --------------------------------------------------------------------------- #
# XML helpers (namespace-agnostic)
# --------------------------------------------------------------------------- #
def _lname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(elem: ET.Element, name: str, default: str = "") -> str:
    for e in elem.iter():
        if _lname(e.tag) == name:
            return (e.text or "").strip()
    return default


def _records_with_child(root: ET.Element, child_name: str) -> list[ET.Element]:
    """Элементы, у которых есть прямой потомок с локальным именем child_name
    (надёжно вычленяет строки-записи независимо от имени типа)."""
    out: list[ET.Element] = []
    for e in root.iter():
        if any(_lname(c.tag) == child_name for c in e):
            out.append(e)
    return out


def _to_float(value: str) -> float:
    text = (value or "").strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _to_int(value: str) -> int:
    try:
        return int(float((value or "0").strip().replace(",", ".")))
    except ValueError:
        return 0


def _xml_escape(value) -> str:
    s = str(value)
    return (
        s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&apos;")
    )


def _raise_if_fault(root: ET.Element) -> None:
    for e in root.iter():
        if _lname(e.tag) == "Fault":
            msg = _child_text(e, "faultstring") or _child_text(e, "Message") or "SOAP Fault"
            raise MikadoError(f"Микадо: {msg}")


class MikadoClient:
    def __init__(
        self,
        client_id: str,
        password: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self.client_id = str(client_id or "").strip()
        self.password = str(password or "")
        self.base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/") + "/"
        self.timeout = timeout

    # -- SOAP transport ----------------------------------------------------- #
    def _soap_action(self, ns: str, method: str) -> str:
        return f"{ns.rstrip('/')}/{method}"

    def _build_envelope(self, ns: str, method: str, params: list[tuple[str, object]]) -> bytes:
        body = "".join(f"<{k}>{_xml_escape(v)}</{k}>" for k, v in params)
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            "<soap:Body>"
            f'<{method} xmlns="{ns}">{body}</{method}>'
            "</soap:Body></soap:Envelope>"
        )
        return xml.encode("utf-8")

    def _call(self, service: str, ns: str, method: str, params: list[tuple[str, object]]) -> ET.Element:
        url = self.base_url + service
        data = self._build_envelope(ns, method, params)
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f'"{self._soap_action(ns, method)}"',
                "User-Agent": "Dazzle-Mikado/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except Exception as exc:  # network/HTTP errors
            raise MikadoError(f"Не удалось обратиться к Микадо ({method}): {exc}") from exc
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise MikadoError(f"Микадо вернул некорректный XML ({method}): {exc}") from exc
        _raise_if_fault(root)
        return root

    # -- public API --------------------------------------------------------- #
    def get_my_ip(self) -> str:
        root = self._call("service.asmx", SERVICE_NS, "Get_MyIP", [])
        return _child_text(root, "Get_MyIPResult")

    def search(self, code: str, *, from_stock_only: bool = False, brand: str = "") -> list[MikadoOffer]:
        params = [
            ("Search_Code", code),
            ("ClientID", self.client_id),
            ("Password", self.password),
            ("FromStockOnly", "FromStockOnly" if from_stock_only else "FromStockAndByOrder"),
        ]
        root = self._call("service.asmx", SERVICE_NS, "Code_Search", params)
        offers: list[MikadoOffer] = []
        for row in _records_with_child(root, "ZakazCode"):
            offers.append(
                MikadoOffer(
                    zakaz_code=_child_text(row, "ZakazCode"),
                    brand=_child_text(row, "Brand"),
                    name=_child_text(row, "Name"),
                    supplier=_child_text(row, "Supplier"),
                    country=_child_text(row, "Country"),
                    producer_code=_child_text(row, "ProducerCode"),
                    price_rur=_to_float(_child_text(row, "PriceRUR")),
                    on_stocks=_child_text(row, "OnStocks"),
                    srok=_child_text(row, "Srock") or _child_text(row, "Srok"),
                    code_type=_child_text(row, "CodeType"),
                    min_qty=_child_text(row, "MinZakazQTY"),
                )
            )
        if brand:
            needle = brand.strip().lower()
            offers = [o for o in offers if needle in o.brand.lower()]
        return offers

    def code_info(self, zakaz_code: str) -> list[MikadoPrice]:
        params = [
            ("ZakazCode", zakaz_code),
            ("ClientID", self.client_id),
            ("Password", self.password),
        ]
        root = self._call("service.asmx", SERVICE_NS, "Code_Info", params)
        prices: list[MikadoPrice] = []
        for row in _records_with_child(root, "PriceRUR"):
            prices.append(
                MikadoPrice(
                    price_rur=_to_float(_child_text(row, "PriceRUR")),
                    currency=_child_text(row, "Currency"),
                    on_stocks=_child_text(row, "OnStocks"),
                    srok=_child_text(row, "Srock") or _child_text(row, "Srok"),
                    srok_max=_child_text(row, "SrockMax"),
                    comment=_child_text(row, "Comment"),
                    delivery_type=_child_text(row, "DeliveryType"),
                    rating=_to_int(_child_text(row, "Rating")),
                )
            )
        return prices

    def basket_add(
        self,
        zakaz_code: str,
        qty: int,
        *,
        notes: str = DEFAULT_NOTE,
        delivery_type: int = 0,
        express_id: int = 0,
        stock_id: int = 0,
    ) -> BasketAddResult:
        """Добавить позицию в корзину Микадо. НЕ оформляет заказ."""
        params = [
            ("ZakazCode", zakaz_code),
            ("QTY", int(qty)),
            ("DeliveryType", int(delivery_type)),
            ("Notes", notes or ""),
            ("ClientID", self.client_id),
            ("Password", self.password),
            ("ExpressID", int(express_id)),
            ("StockID", int(stock_id)),
        ]
        root = self._call("basket.asmx", BASKET_NS, "Basket_Add", params)
        return BasketAddResult(
            message=_child_text(root, "Message"),
            id=_to_int(_child_text(root, "ID")),
            ordered_qty=_to_int(_child_text(root, "OrderedQTY")),
            ordered_code=_child_text(root, "OrderedCode"),
        )

    def basket_list(self) -> list[BasketLine]:
        params = [("ClientID", self.client_id), ("Password", self.password)]
        root = self._call("basket.asmx", BASKET_NS, "Basket_List", params)
        lines: list[BasketLine] = []
        for row in _records_with_child(root, "ZakazCode"):
            lines.append(
                BasketLine(
                    id=_to_int(_child_text(row, "ID")),
                    zakaz_code=_child_text(row, "ZakazCode"),
                    name=_child_text(row, "Name"),
                    qty=_to_float(_child_text(row, "QTY")),
                    price_rur=_to_float(_child_text(row, "PriceRUR")),
                    status=_child_text(row, "Status"),
                    srok=_child_text(row, "Srok") or _child_text(row, "Srock"),
                    notes=_child_text(row, "Notes"),
                )
            )
        return lines
