# INT-PARSING：同一个数字串，三套取整标准

基线：werkzeug 3.1.8（本仓库 `src`，与 venv 的 editable 目标内容一致），
在仓库根目录用 `.venv/bin/python repro/int-parsing-two-standards.py` 实测。
四本相关测试（routing / http / wrappers / datastructures）基线全绿：458 passed。

## 一、三组读数（原样照抄，未改任何代码）

```
URL 段 <int>  vs  同一串当 Content-Length:
  '3'      -> route={'i': 3}         content_length=3
  '٣'      -> route={'i': 3}         content_length=0
  '１２'     -> route={'i': 12}        content_length=0
  '🯱🯲🯳'    -> route={'i': 123}       content_length=0
  '1_0'    -> route=NotFound         content_length=0
  ' 5'     -> route=NotFound         content_length=5
  两种写法落同一值: True | build 只产得出: /item/3
直接调 to_python（自定义 converter 就这么用）:
  int  : {'1_0': 10, ' 5': 5, '5\n': 5, '+5': 5, '-0': 0, '0x10': 'ValueError'}
  float: {'1e3': 1000.0, 'inf': inf, 'nan': nan, '1_0.5': 10.5}
  min=0,max=1 拦住 inf: ValidationError 拦不住 nan: nan
第三套口径：Headers.get(type=int)（纯 int() 语义）:
  '3'      -> 3
  '٣'      -> 3
  '１２'     -> 12
  '1_0'    -> 10
  ' 5'     -> 5
  '-0'     -> 0
  '+5'     -> 5
  '1e3'    -> None
```

## 二、三套各自靠什么判定

1. **路由 `<int:>` 转换器** —— `src/werkzeug/routing/converters.py:195` `regex = r"\d+"`，
   未加 `re.ASCII`。Python 的 `\d` 默认按 Unicode 匹配所有十进制数字
   （阿拉伯-印度数字 `٣`、全角 `１２`、分段数字 `🯱🯲🯳` 都算），整段必须全是数字，
   所以空格、下划线、符号一律匹配不上（NotFound）。匹配上之后再走
   `num_convert=int`（`converters.py:136`），而 `int()` 本来就收 Unicode 数字，
   于是 `/item/٣` 解析成 3。但 `to_url` 只会 `str(int(...))`，
   所以 build 永远只产得出 ASCII 的 `/item/3`——收得进、产不出。
2. **Content-Length** —— `src/werkzeug/_internal.py:196`
   `_plain_int_re = re.compile(r"-?\d+", re.ASCII)`，先 `strip()` 再 **fullmatch**，
   只认 ASCII 数字和可选负号，明确拒绝 `+`、`_`、非 ASCII 数字（docstring 原话：
   这些 int() 收但 HTTP 头里不允许）。失败抛 `ValueError`，
   由 `src/werkzeug/sansio/utils.py:222` 兜成 `0`。所以 `' 5'` 能出 5（strip 的功劳），
   `٣`/`１２`/`🯱🯲🯳`/`1_0` 全部落 0。
3. **`Headers.get(type=int)`** —— `src/werkzeug/datastructures/headers.py:159`
   就是 `type(rv)` 即纯 `int()`，抛 `ValueError` 就返回 default（None）。
   纯 `int()` 语义：收 Unicode 数字、收下划线分组（`1_0`→10）、收首尾空白、
   收 `+`/`-` 号；`1e3` 不是十进制整数字面量，抛错 → None。

另外脚本第二组暴露的是**第四套**：直接调 `to_python`
（`converters.py:151`）不做任何正则把关，等于裸 `int()`/`float()`，
自定义 converter 抄基类就这么用。float 侧 `float("inf")`/`float("nan")` 都合法，
`min`/`max` 用 `<`/`>` 比较（`converters.py:155`），`inf > 1` 为真所以拦得住，
而 `nan` 与任何值比较都为假，两个 if 都不触发——`nan` 穿闸而过。

## 三、一个三套结论互不相同的输入

**`'1_0'`**（实测，基线代码）：

- 路由 `<int:>`：**匹配不上**（NotFound，下划线不在 `\d` 里）；
- Content-Length：**0**（`_plain_int` 拒下划线，异常兜成 0）；
- `Headers.get(type=int)`：**10**（`int("1_0")` 的下划线分组语义）。

同一串，"非法 / 0 / 10" 三种答案。（直接调 `to_python` 也得 10，与第三套同源。）

## 四、实测：两条单边的收敛尝试

仓库拷到仓库外两份（venv 是 `werkzeug.pth` 的 editable 安装，
跑拷贝时自带 `PYTHONPATH=<拷贝>/src` 指回拷贝自己，已用
`werkzeug.__file__` 验证导入的确实是拷贝）。实现与测试一个字未动。

### 拷贝 A `/tmp/wz-ascii`：路由正则收严成纯 ASCII 数字

改动：`converters.py` 中 `IntegerConverter.regex` 由 `r"\d+"` 改为 `r"[0-9]+"`。

重跑脚本完整输出：

```
URL 段 <int>  vs  同一串当 Content-Length:
  '3'      -> route={'i': 3}         content_length=3
  '٣'      -> route=NotFound         content_length=0
  '１２'     -> route=NotFound         content_length=0
  '🯱🯲🯳'    -> route=NotFound         content_length=0
  '1_0'    -> route=NotFound         content_length=0
  ' 5'     -> route=NotFound         content_length=5
  两种写法落同一值: False | build 只产得出: /item/3
直接调 to_python（自定义 converter 就这么用）:
  int  : {'1_0': 10, ' 5': 5, '5\n': 5, '+5': 5, '-0': 0, '0x10': 'ValueError'}
  float: {'1e3': 1000.0, 'inf': inf, 'nan': nan, '1_0.5': 10.5}
  min=0,max=1 拦住 inf: ValidationError 拦不住 nan: nan
第三套口径：Headers.get(type=int)（纯 int() 语义）:
  '3'      -> 3
  '٣'      -> 3
  '１２'     -> 12
  '1_0'    -> 10
  ' 5'     -> 5
  '-0'     -> 0
  '+5'     -> 5
  '1e3'    -> None
```

变化集中在第一组：`٣`/`１２`/`🯱🯲🯳` 三行 route 由解析成功变为 NotFound，
`两种写法落同一值` 由 True 变 False；to_python、Headers.get 两组逐字不变。

四本测试：`tests/test_routing.py tests/test_http.py tests/test_wrappers.py
tests/test_datastructures.py` → **458 passed，红清单为空**。
注意这不等于无行为变化：上面三行读数明显变了，只是这四本没有任何用例
钉住"Unicode 数字能进路由"这一行为。

残留分歧：`' 5'` 仍是 route=NotFound vs content_length=5（路由不 strip）；
`'1_0'` 仍是 route=NotFound vs Headers.get→10；to_python 那组原封不动
（`'1_0'`→10、`' 5'`→5、`'+5'`→5）。而且 `FloatConverter.regex = r"\d+\.\d+"`
没动，浮点路由照样收 Unicode 数字——整数收严了，浮点还开着。

### 拷贝 B `/tmp/wz-unicode`：Content-Length 判定放宽成收 Unicode 数字

改动：`_internal.py` 中 `_plain_int_re` 由 `re.compile(r"-?\d+", re.ASCII)`
改为 `re.compile(r"-?\d+")`（去掉 `re.ASCII`）。

重跑脚本完整输出：

```
URL 段 <int>  vs  同一串当 Content-Length:
  '3'      -> route={'i': 3}         content_length=3
  '٣'      -> route={'i': 3}         content_length=3
  '１２'     -> route={'i': 12}        content_length=12
  '🯱🯲🯳'    -> route={'i': 123}       content_length=123
  '1_0'    -> route=NotFound         content_length=0
  ' 5'     -> route=NotFound         content_length=5
  两种写法落同一值: True | build 只产得出: /item/3
直接调 to_python（自定义 converter 就这么用）:
  int  : {'1_0': 10, ' 5': 5, '5\n': 5, '+5': 5, '-0': 0, '0x10': 'ValueError'}
  float: {'1e3': 1000.0, 'inf': inf, 'nan': nan, '1_0.5': 10.5}
  min=0,max=1 拦住 inf: ValidationError 拦不住 nan: nan
第三套口径：Headers.get(type=int)（纯 int() 语义）:
  '3'      -> 3
  '٣'      -> 3
  '１２'     -> 12
  '1_0'    -> 10
  ' 5'     -> 5
  '-0'     -> 0
  '+5'     -> 5
  '1e3'    -> None
```

变化集中在第一组：`٣`/`１２`/`🯱🯲🯳` 三行 content_length 由 0 变为
3 / 12 / 123，与路由读数对齐；`'1_0'`、`' 5'` 两行及后两组逐字不变。

四本测试：**1 failed, 457 passed**，红清单：

```
FAILED tests/test_http.py::test_content_range_invalid_int[*/\U0001fbf1\U0001fbf2\U0001fbf3]
```

原因：`_plain_int` 是公共件，除了 `get_content_length`
（`src/werkzeug/sansio/utils.py:222`），还被 `parse_content_range_header` /
`parse_range_header`（`src/werkzeug/http.py:854` 起）、multipart 解析
（`src/werkzeug/formparser.py:339`）、`FileStorage.content_length`
（`src/werkzeug/datastructures/file_storage.py:74`）共用。放宽一个旋钮，
Range / Content-Range / 上传解析全部跟着放宽——`bytes */🯱🯲🯳`
现在被解析成 `<ContentRange 'bytes */123'>` 而不是判非法，
正中 test_http 里专门防这一手的用例。

残留分歧：路由与 Content-Length 在六个 URL 测试串上数字口径对齐了，
但 `' 5'` 仍是 route=NotFound vs content_length=5；`'1_0'` 仍是
route=NotFound、content_length=0、Headers.get→10 三方分裂
（下划线、正号、空白这些 `int()` 特性两边都没碰）。

### 为什么哪条单独都走不到统一

- 三套的分歧不只在"数字的字母表"，还在**词法层**：strip 不 strip、
  收不收下划线/正号、fullmatch 还是裸 `int()`。A 只统一了路由与
  `_plain_int` 的数字字母表，B 只统一了 `_plain_int` 与路由的字母表，
  两次实验后 `' 5'`、`'1_0'` 依然是分裂输入——词法差异一条都没碰。
- `Headers.get(type=int)` 的 `type` 是用户传入的回调，语义就是
  "调一下、ValueError 当缺省"，这是公开 API 契约，改不动；
  `to_python` 裸奔同理（自定义 converter 直接继承使用）。
- B 还证明 `_plain_int` 不是 Content-Length 的私有开关，
  单边放宽会把 Range/Content-Range/multipart 一起拖下水，
  并立刻被现有测试抓红。

## 五、主张的收敛方向

向最严的 `_plain_int` 看齐：**URL 与 HTTP 头都是 ASCII 协议，
数字一律只认 ASCII `0-9`**。具体是路由侧 `IntegerConverter`（及
`FloatConverter`）正则改 `[0-9]` 或编译时加 `re.ASCII`，与
`_plain_int` 对齐；`Headers.get(type=int)` 与 `to_python` 维持
`int()` 语义不动（公开契约），在文档里写明"转换回调不做输入校验，
校验在路由正则/头部解析层"。这样"收得进的必然 build 得出来"，
`route('٣') == route('3')` 这类同值不同串的隐患也随之消失。

代价：会新弄坏两类现网地址（今天在基线上都能正常路由）：

1. **阿拉伯-印度数字地址**：`/item/٣`（U+0663），今天路由成 `i=3`，
   收严后 404。
2. **全角数字地址**：`/item/１２`（U+FF11 U+FF12），今天路由成 `i=12`，
   收严后 404。

（同理还有分段数字 `/item/🯱🯲🯳` → 123 这类更冷门的 Unicode 十进制数字地址。）
