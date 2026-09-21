# 字符串取整数：同包三套口径

基线：werkzeug 3.1.8（本仓库 `src/`），复现脚本 `repro/int-parsing-two-standards.py`，
解释器 `.venv/bin/python`。下文所有读数均为实测原文，未做改写；“匹配不上”对应
路由的 `NotFound`，“报错”对应被转成异常类名字符串的那一侧。

## 1. 基线脚本逐行读数

命令：

```
.venv/bin/python repro/int-parsing-two-standards.py
```

输出（逐字）：

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

### 4.4 四本测试的红清单

命令（两边相同，只换目录）：

```
PYTHONPATH=src <venv>/bin/python -m pytest \
  tests/test_routing.py tests/test_http.py \
  tests/test_wrappers.py tests/test_datastructures.py -q
```

- copyA（路由收严）：**458 passed，红清单为空。**
  - `tests/test_routing.py`：无红（现有用例没有断言 Unicode 数字命中 `<int>`）。
  - `tests/test_http.py`、`tests/test_wrappers.py`、
    `tests/test_datastructures.py`：无红（改动不触及这些模块）。
- copyB（Content-Length 放宽）：**457 passed, 1 failed**，红清单一条：
  - `tests/test_http.py::test_content_range_invalid_int[*/\U0001fbf1\U0001fbf2\U0001fbf3]`
    —— 用例断言 `parse_content_range_header("bytes */🯱🯲🯳") is None`；放宽后
    `🯱🯲🯳` 被 `_plain_int` 接受成 123，返回 `<ContentRange 'bytes */123'>`，
    断言失败。同组的 `"1-+2/3"`、`"1_23-125/*"` 仍为 None（去 ASCII 标志
    并不放开 `+` 和下划线），所以只有这一条红。
  - 其余三本：`tests/test_routing.py`、`tests/test_wrappers.py`、
    `tests/test_datastructures.py` 无红。

四本之外，全量 `pytest tests` 里 copyB 还多打红一条（同一放宽的直接受害者，
记录在此供参考，不计入上面四本清单）：

- `tests/sansio/test_request.py::test_content_length[headers6-0]`
  —— 参数表断言 `Headers({"Content-Length": "🯱🯲🯳"})` 的 `content_length`
  为 `0`，放宽后变成 `123`。同表 `"+123"`、`"1_23"` 仍为 0。

全量跑里另有 `tests/test_serving.py`、`test_debug.py`、
`tests/middleware/test_http_proxy.py` 的 `PermissionError: [Errno 1]`，在未改动的
基线上同样失败，是本沙箱不允许绑定端口的环境问题，与两处改动无关。

## 5. 读数里残留的分歧

### copyA 残留（只收严路由之后）

- `' 5'`：路由 NotFound，Content-Length 5——HTTP 侧 strip 空白、路由正则不收空白。
- `'1_0'`：路由 NotFound，Content-Length 0，`Headers.get` 10——三边仍三个结论。
- `'+5'`：NotFound / 0 / 5（第 3 节那个串原样保留）。
- `'٣'`、`'１２'`：路由与 Content-Length 现在一致了（都不认），但
  `Headers.get(type=int)` 仍给出 3、12——口径 C 没被碰到。
- 第二组原样残留：直接 `to_python` 仍收 `1_0`/` 5`/`+5`；float 仍收
  `inf`/`nan`，`min=0,max=1` 仍拦不住 `nan`。
- `<float>` 路由没改，仍收 Unicode 数字：实测 `/p/١.٥` → `{'x': 1.5}`、
  `/p/１.２５` → `{'x': 1.25}`（其 `regex=r"\d+\.\d+"` 同样未加 ASCII）。

### copyB 残留（只放宽 Content-Length 之后）

- `'1_0'`：路由 NotFound，Content-Length 0，`Headers.get` 10——三边仍三个结论。
- `' 5'`：路由 NotFound 与 Content-Length 5 的分歧仍在。
- `'+5'`：NotFound / 0 / 5 原样残留；`"-6"` 仍被 `max(0, …)` 夹成 0。
- 第二组原样残留（`1_0→10`、`inf`、`nan`、拦不住 `nan`），第三组
  `Headers.get` 一字未变。

### 为什么哪条单独都走不到统一

分歧有**两个互相独立的轴**，而每处补丁只拨了一个轴上的一个点：

1. **字符集轴（Unicode `\d` vs ASCII `[0-9]`）**：路由正则与 `_plain_int`
   各写了一份 `\d+`，一份没加 `re.ASCII`、一份加了。copyA 只改了 int 转换器
   那一份（float 转换器还是 Unicode 宽口径）；copyB 只改了 HTTP 那一份，
   而且改完直接违反 HTTP 语法（RFC 9110 的字段语法只含 ASCII 数字），测试
   立刻见红。
2. **字面量语义轴（内建 `int()`/`float()` vs 严格 fullmatch）**：
   `Headers.get(type=int)` 是“把任意 callable 套到头值上”的通用钩子，
   `int` 的下划线、空白、`+`、Unicode 数字语义是 Python 语言语义；
   `NumberConverter.to_python` 直接调 `num_convert` 且可绕过正则。
   两处补丁都不碰这条轴，所以 `1_0`、` 5`、`+5` 的三边分裂在两份拷贝里
   原样保留；float 侧的 `nan` 比较漏洞也与字符集无关，两边都拦不住。

即：copyA 让“路由 vs Content-Length”在 Unicode 数字上对齐，却留下空白、
下划线、`+`、float、直调 `to_python` 和 `Headers.get`；copyB 让
“路由 vs Content-Length”在 Unicode 数字上以另一种方式对齐，却以违反 HTTP
语法为代价（1+1 条测试变红），其余分歧一条没消。

## 6. 主张的收敛方向

向**严格 ASCII 十进制**收敛（即 copyA 的方向，但做完整），而不是向 Unicode
放宽：

1. 路由数字转换器统一用 ASCII 字符类：`IntegerConverter.regex` 用 `[0-9]+`，
   `FloatConverter.regex` 同步用 `[0-9]+\.[0-9]+`（含 `signed` 变体只加 ASCII
   `-`）。理由是 URL build 端 `to_url` 本来就只产 ASCII，路由系统应以
   “build 出来的形态”为规范形态；HTTP 侧的 `_plain_int` 已证明 ASCII 口径是
   框架在协议边界上的既定选择。
2. 让匹配门和转换门共用同一个严格解析器（例如让
   `NumberConverter.to_python` 也走与 `_plain_int` 同源的校验，而不是裸
   `int(value)`），消掉“正则匹配不上、直调 `to_python` 却收下 `1_0`/` 5`”
   的第二套口径；float 侧在 min/max 之外显式拒绝 `math.isnan`/`isinf`
   （或用严格 fullmatch 先卡住 `inf`/`nan` 字样）。
3. `Headers.get(type=int)` **不强行统一**：它的契约是“应用户要求调用
   callable”，内建 `int` 的语义属于 Python；在文档里明确
   `type=int` ≠ 严格 HTTP 整数，需要 HTTP 口径的头（Content-Length、Range 等）
   继续用框架自带的严格属性/解析函数。能统一的是框架自己内部的数字入口，
   不是这个通用 cast 钩子。

第 1 步会新弄坏两类现网能 200 命中的地址（基线上经 werkzeug 测试客户端实测，
PATH_INFO 已完成百分号解码，当前均命中 `{'i': N}`，收严后变 404 NotFound）：

- **非拉丁文种的十进制数字路径段**——阿拉伯-印度数字串，例如原始路径
  `/item/٣`（线上通常以百分号编码形式出现：`/item/%D9%A3`），基线命中
  `{'i': 3}`，收严后 404。
- **全角（宽体）数字路径段**——例如 `/item/１２`（编码形态
  `/item/%EF%BC%91%EF%BC%92`），基线命中 `{'i': 12}`，收严后 404；
  同族的分段数字 `/item/🯱🯲🯳`（编码形态
  `/item/%F0%9F%AF%B1%F0%9F%AF%B2%F0%9F%AF%B3`，命中 123）也属此类。

迁移办法也明确：这些地址本就只有 ASCII 一条 build 产物（`/item/3`、
`/item/12`），受影响方应把入站链接规范化到 ASCII，或在前面挂一条重写/301。


三组即：

1. 第一组：`<int>` 路由段 vs 同一串作为 `Content-Length`（6 行 + 1 行汇总）。
2. 第二组：绕过匹配、直接调 `IntegerConverter.to_python` / `FloatConverter.to_python`
   （2 行 dict + 1 行 min/max）。
3. 第三组：`Headers.get(key, type=int)`（8 行）。

## 2. 三套口径各自靠什么判定

### 口径 A：路由 `<int>`（URL 段匹配）

判定分两道门，字符串先过门一才到门二：

- 门一（正则）：`src/werkzeug/routing/converters.py` 里
  `IntegerConverter.regex = r"\d+"`，**没有** `re.ASCII`。Python 的 `\d` 在默认
  Unicode 模式下匹配全部 Unicode 十进制数字（`unicodedata.category` 为 `Nd`，
  `str.isdigit()` 为真），所以阿拉伯-印度数字 `٣`(U+0663)、全角 `１２`
  (U+FF11/U+FF12)、分段数字 `🯱🯲🯳`(U+1FBF1..3) 全部命中；下划线、空格、`+`
  不命中，段不匹配即规则不匹配，表现为 `NotFound`（匹配不上）。
- 门二（转换）：`NumberConverter.to_python` 调 `self.num_convert(value)`，
  int 转换器的 `num_convert = int`，即内建 `int()`。正则保证过门一的子串
  `int()` 一定成功（`signed=True` 时正则变 `-?\d+`，注意只认 ASCII `-`）。
- 方向不对称：`to_url` 用 `str(int(value))` 产出，build 永远只能生成 ASCII
  `/item/3`；于是 `٣` 和 `3` 匹配进来落同一个参数字典 `{'i': 3}`，却只有一条
  规范 URL（读数里的“两种写法落同一值: True”）。

### 口径 B：HTTP 头整数（`Content-Length`，以及 Range/Content-Range 等）

`src/werkzeug/_internal.py`：

```python
_plain_int_re = re.compile(r"-?\d+", re.ASCII)

def _plain_int(value: str) -> int:
    value = value.strip()
    if _plain_int_re.fullmatch(value) is None:
        raise ValueError
    return int(value)
```

- **带 `re.ASCII` 的 fullmatch**：整串（先 `strip()` 两端空白）只能由 ASCII
  `0-9` 和至多一个前导 `-` 构成。Unicode 数字、`+`、下划线一律 `ValueError`。
- `Content-Length` 走 `src/werkzeug/sansio/utils.py` 的
  `max(0, _plain_int(value))`，捕获 `ValueError` 返回 `0`；所以 `٣`、`１２`、
  `🯱🯲🯳`、`1_0` 都被拒成 `0`，而带空格的 ` 5` 因先 strip 得到 `5`。负值
  `-6` 能过正则但被 `max(0, …)` 夹成 `0`。
- 同一个 `_plain_int` 还被 `http.py` 的 Range/Content-Range 解析和
  `file_storage.py` 复用，这是刻意贴合 HTTP 语法的严格口径（头里不允许
  Unicode 数字、`+`、下划线）。

### 口径 C：`Headers.get(key, type=int)`

`src/werkzeug/datastructures/headers.py` 的 `get` 只是
`try: type(value) … except ValueError: 返回默认值`。传入内建 `int()` 时就是
纯粹的 Python 字面量语义：

- 接受 Unicode 数字（`int("٣") == 3`、`int("１２") == 12`）；
- 接受 PEP 515 下划线（`int("1_0") == 10`）；
- 接受两端空白（`int(" 5") == 5`、`int("5\n") == 5`）；
- 接受显式正号（`int("+5") == 5`）；
- 但不接受非十进制前缀（`int("0x10")` 抛 `ValueError` → 读数里报错），
  不接受浮点字面量（`int("1e3")` 抛 `ValueError` → 取不到值返回 `None`）。

### 附：第二组读数为什么又是一套

直接调 `ci.to_python("1_0")` 跳过了门一正则，只剩 `int()`，因此路由匹配不上
的串在这里能出 10；` 5`、`5\n`、`+5` 同理，`0x10` 仍 `ValueError`。
`FloatConverter` 的 `num_convert = float`：`1e3 → 1000.0`、`inf`/`nan` 照收、
`1_0.5 → 10.5`；而 min/max 边界检查是裸比较——`inf > 1` 能拦住，
`nan` 的一切比较都是 False，所以 `min=0,max=1` **拦不住 `nan`**。

## 3. 新造的三边互异输入：`"+5"`

脚本读数里没有这个串。在基线上对三边实测（`Rule("/item/<int:i>")`、
同一串作 `Content-Length`、`Headers.get("X", type=int)`）：

```
'+5'         route='NotFound'     content_length=0    headers.get=5
```

- 路由（口径 A）：`\d+` 不接受前导 `+` → 匹配不上（`NotFound`）。
- Content-Length（口径 B）：`-?\d+` 带 `re.ASCII` 的 fullmatch 不接受 `+`
  → `_plain_int` 抛 `ValueError` → `content_length = 0`。
- Headers.get(type=int)（口径 C）：内建 `int("+5") == 5` → 得到 `5`。

同一串 `+5`，三边结论分别是 **匹配不上 / 0 / 5**，两两不同。
（同类可复现串还有 `'1_0'`：路由 NotFound、Content-Length 0、Headers 得 10，
但它已在脚本第一、三组出现，故另选 `+5`。）

## 4. 仓库外两份拷贝的相反实验

### 4.1 拷贝与运行方式

两份拷贝都在仓库外，且不带 `.venv`（venv 是可编辑安装，直接复用会指回原仓库）：

```
rsync -a --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
  /home/liuyang/gsb/repos/t42-werkzeug/ /tmp/int-exp/copyA/
rsync -a --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
  /home/liuyang/gsb/repos/t42-werkzeug/ /tmp/int-exp/copyB/
```

跑拷贝时解释器仍用原 venv，但用 `PYTHONPATH=src` 指回**拷贝自己**的源码：

```
cd /tmp/int-exp/copyA && PYTHONPATH=src \
  /home/liuyang/gsb/repos/t42-werkzeug/.venv/bin/python repro/int-parsing-two-standards.py
```

改动（各一处，实现与测试的其余部分一字未动）：

- copyA（收严路由）：`src/werkzeug/routing/converters.py`
  `IntegerConverter.regex = r"\d+"` → `r"[0-9]+"`。
- copyB（放宽 Content-Length）：`src/werkzeug/_internal.py`
  `re.compile(r"-?\d+", re.ASCII)` → `re.compile(r"-?\d+")`（去掉 ASCII 标志，
  `\d` 回到 Unicode 语义）。

### 4.2 copyA（路由收严成纯 ASCII 数字）读数

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

### 4.3 copyB（Content-Length 放宽收 Unicode 数字）读数

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
