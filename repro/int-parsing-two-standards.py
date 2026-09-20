r"""wz-4 起点 3.1.8: 同包内两个「字符串取整数」实现宽严相反。
converters.py: IntegerConverter.regex = r"\d+" (未加 re.ASCII), num_convert=int
_internal.py:  _plain_int_re = re.compile(r"-?\d+", re.ASCII)   <- Content-Length 用
"""
from werkzeug.datastructures import Headers
from werkzeug.routing import Map, Rule
from werkzeug.routing.converters import FloatConverter, IntegerConverter
from werkzeug.sansio.request import Request

m = Map([Rule("/item/<int:i>", endpoint="item")])
ad = m.bind("example.com")
ci, cf = IntegerConverter(m), FloatConverter(m)


def call(fn, v):
    try:
        return fn(v)
    except Exception as e:
        return f"{type(e).__name__}"


def route(v):
    return str(call(lambda p: ad.match(p)[1], "/item/" + v))


def cl(v):
    r = Request("POST", "http", None, "", "", b"", Headers({"Content-Length": v}), None)
    return r.content_length


print("URL 段 <int>  vs  同一串当 Content-Length:")
for v in ["3", "٣", "１２", "🯱🯲🯳", "1_0", " 5"]:
    print(f"  {v!r:8} -> route={route(v):16} content_length={cl(v)}")
print("  两种写法落同一值:", route("٣") == route("3"),
      "| build 只产得出:", ad.build("item", {"i": 3}))
print("直接调 to_python（自定义 converter 就这么用）:")
print("  int  :", {v: call(ci.to_python, v) for v in ["1_0", " 5", "5\n", "+5", "-0", "0x10"]})
print("  float:", {v: call(cf.to_python, v) for v in ["1e3", "inf", "nan", "1_0.5"]})
b = FloatConverter(m, min=0, max=1)
print("  min=0,max=1 拦住 inf:", call(b.to_python, "inf"), "拦不住 nan:", repr(call(b.to_python, "nan")))

print("第三套口径：Headers.get(type=int)（纯 int() 语义）:")
h = Headers({"X": "0"})
for v in ["3", "٣", "１２", "1_0", " 5", "-0", "+5", "1e3"]:
    h.set("X", v)
    try:
        got = h.get("X", type=int)
    except Exception as e:
        got = type(e).__name__
    print(f"  {v!r:8} -> {got!r}")
