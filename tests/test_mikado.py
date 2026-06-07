"""Тесты SOAP-клиента Микадо: парсинг ответов из XML-фикстур + инвариант
безопасности (нет метода оформления заказа)."""
import xml.etree.ElementTree as ET

import pytest

from tirika_importer.mikado import (
    MikadoClient,
    MikadoError,
    _raise_if_fault,
    _to_float,
    _xml_escape,
)

CODE_SEARCH_XML = """<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
 <soap:Body>
  <Code_SearchResponse xmlns="http://mikado-parts.ru/service">
   <Code_SearchResult>
    <Code_Search>BS-1010</Code_Search>
    <List>
     <Code_List_Row>
      <ZakazCode>BS-1010</ZakazCode><Supplier>Mikado</Supplier>
      <ProducerBrand>Zekkert</ProducerBrand><ProducerCode>BS1010</ProducerCode>
      <Brand>Zekkert</Brand><Country>DE</Country><Name>Колодки тормозные</Name>
      <OnStocks>40</OnStocks><PriceRUR>1250.00</PriceRUR><Srock>1</Srock>
      <CodeType>Aftermarket</CodeType><MinZakazQTY>1</MinZakazQTY>
     </Code_List_Row>
     <Code_List_Row>
      <ZakazCode>BS-1010</ZakazCode><Brand>Bosch</Brand><Name>Колодки</Name>
      <PriceRUR>1 500,00</PriceRUR><OnStocks>5</OnStocks><Srock>3</Srock>
     </Code_List_Row>
    </List>
   </Code_SearchResult>
  </Code_SearchResponse>
 </soap:Body>
</soap:Envelope>"""

CODE_INFO_XML = """<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
 <soap:Body>
  <Code_InfoResponse xmlns="http://mikado-parts.ru/service">
   <Code_InfoResult>
    <Code>BS-1010</Code><Brand>Zekkert</Brand><Name>Колодки</Name>
    <Prices>
     <Code_PriceInfo>
      <PriceRUR>1250.00</PriceRUR><Currency>RUR</Currency><OnStocks>40</OnStocks>
      <Srock>1</Srock><SrockMax>2</SrockMax><Comment>МСК</Comment>
      <DeliveryType>1</DeliveryType><Rating>5</Rating>
     </Code_PriceInfo>
     <Code_PriceInfo><PriceRUR>1180.00</PriceRUR><Srock>5</Srock></Code_PriceInfo>
    </Prices>
   </Code_InfoResult>
  </Code_InfoResponse>
 </soap:Body>
</soap:Envelope>"""

BASKET_ADD_XML = """<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
 <soap:Body>
  <Basket_AddResponse xmlns="http://mikado-parts.ru/ws1/">
   <Basket_AddResult>
    <Message>OK</Message><ID>12345</ID><OrderedQTY>4</OrderedQTY>
    <OrderedCode>BS-1010</OrderedCode>
   </Basket_AddResult>
  </Basket_AddResponse>
 </soap:Body>
</soap:Envelope>"""

BASKET_LIST_XML = """<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
 <soap:Body>
  <Basket_ListResponse xmlns="http://mikado-parts.ru/ws1/">
   <Basket_ListResult>
    <BasketItem>
     <ID>1</ID><ZakazCode>BS-1010</ZakazCode><Name>Колодки</Name><QTY>4</QTY>
     <Price>1250</Price><PriceRUR>1250.00</PriceRUR><Status>Stock</Status>
     <Express/><Srok>1</Srok><Notes>Dazzle</Notes>
    </BasketItem>
    <BasketItem>
     <ID>2</ID><ZakazCode>DF-3215</ZakazCode><Name>Диск</Name><QTY>2</QTY>
     <PriceRUR>2940.00</PriceRUR><Status>Zakaz</Status><Srok>3</Srok><Notes>Dazzle</Notes>
    </BasketItem>
   </Basket_ListResult>
  </Basket_ListResponse>
 </soap:Body>
</soap:Envelope>"""

FAULT_XML = """<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
 <soap:Body><soap:Fault>
  <faultcode>soap:Server</faultcode><faultstring>Доступ запрещён</faultstring>
 </soap:Fault></soap:Body>
</soap:Envelope>"""


def _client_returning(xml: str) -> MikadoClient:
    c = MikadoClient("00000", "secret")
    c._call = lambda *a, **k: ET.fromstring(xml)  # type: ignore[assignment]
    return c


def test_search_parses_offers():
    offers = _client_returning(CODE_SEARCH_XML).search("BS-1010")
    assert len(offers) == 2
    assert offers[0].brand == "Zekkert"
    assert offers[0].price_rur == 1250.0
    assert offers[1].price_rur == 1500.0  # "1 500,00" → 1500.0


def test_search_brand_filter():
    offers = _client_returning(CODE_SEARCH_XML).search("BS-1010", brand="Zekkert")
    assert len(offers) == 1
    assert offers[0].brand == "Zekkert"


def test_code_info_parses_prices():
    prices = _client_returning(CODE_INFO_XML).code_info("BS-1010")
    assert len(prices) == 2
    assert prices[0].price_rur == 1250.0
    assert prices[0].srok == "1"
    assert prices[0].delivery_type == "1"
    assert prices[0].rating == 5


def test_basket_add_parses_result():
    res = _client_returning(BASKET_ADD_XML).basket_add("BS-1010", 4, notes="Dazzle")
    assert res.message == "OK"
    assert res.id == 12345
    assert res.ordered_qty == 4
    assert res.ordered_code == "BS-1010"


def test_basket_list_parses_lines_with_notes():
    lines = _client_returning(BASKET_LIST_XML).basket_list()
    assert len(lines) == 2
    assert lines[0].notes == "Dazzle"
    assert lines[0].qty == 4.0
    assert lines[0].status == "Stock"
    assert lines[1].zakaz_code == "DF-3215"


def test_soap_fault_raises():
    with pytest.raises(MikadoError):
        _raise_if_fault(ET.fromstring(FAULT_XML))


def test_helpers():
    assert _to_float("1 250,00") == 1250.0
    assert _to_float("") == 0.0
    assert _xml_escape("a&b<c>") == "a&amp;b&lt;c&gt;"


def test_no_order_submit_method():
    """Инвариант безопасности: клиент НЕ умеет оформлять/отправлять заказ —
    только корзина. Финал — вручную в кабинете Микадо."""
    forbidden = ("submit", "place_order", "confirm_order", "send_order", "checkout", "order_create")
    names = [n.lower() for n in dir(MikadoClient) if not n.startswith("__")]
    for n in names:
        assert not any(bad in n for bad in forbidden), f"unexpected order-submit method: {n}"
