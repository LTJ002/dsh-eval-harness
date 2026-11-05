# 随附资产

沿用本目录的文件即可搭起最小可用的评测体系，不必从零写。

| 文件 | 用途 | 依赖 |
|---|---|---|
| `mutation_check.py` | **变异测试**：把实现改坏，验证断言会不会翻红。加判据后必跑 | 仅标准库 |
| `selftest.py` | **自检**：判据与分母纪律的回归测试，改任何脚本后必跑 | 仅标准库 |
| `eval_results.py` | 结果落盘（分片写入 + `kind` 字段，避免并发覆盖） | 仅标准库 |
| `eval_baseline.py` | 基线对比：**按绝对条数**判退化，offline/live-strict/live 分严格度，附 Wilson 置信区间与用例级 diff，CI 卡点 | 仅标准库 |
| `eval_online.py` | 在线评测骨架：`tool` / `inject` / `answer` 三个套件 | 仅标准库 |
| `eval_rag.py` | RAG 检索层指标：Recall@K / MRR / nDCG@K / Precision@K，双门（完全命中进基线 + 可选阈值） | 仅标准库 |
| `eval_manifest.py` | 运行清单：提示词/数据集 sha256 指纹 + config + diff | 仅标准库 |
| `ci-eval.yml.example` | CI/CD 三 gate 模板（自检+变异 / 离线基线 / 在线定时） | GitHub Actions |
| `EvalResults.java` | JUnit 场景的结果落盘，JSON 形状与 Python 版一致（含 `kind` 字段） | JDK 17 |
| `install.ps1` | 把 bundle 从仓库副本装到 `~/.dsh/skills/`；`-VerifyOnly` 检查两份是否分叉 | PowerShell |
| `datasets/*.example.jsonl` | 数据集样例 | — |

> **为什么要 install.ps1**：bundle 存在两份（仓库副本 + 用户级）。手动复制会让它们
> 静默分叉——本次编写过程中就真的分叉过三个文件，之后按哪一份跑全凭运气。
> 脚本每次全量重装并可校验一致性。**只能从仓库副本运行**：从安装副本运行会被拒绝，
> 因为那时源与目标同目录，"清理后重装"会删掉它自己刚装好的 skill。

> **不要在这份文档里写死自检条数**。自检会随判据增加而变长，写死的数字必然陈旧——
> 那正是本 skill 反复警告的错误。跑 `python selftest.py`，看末行"全部通过"即可。

## 五条正确的实现，照抄即可

`eval_online.py` 不是"随便写写的骨架"，它固化了五种会让评测说谎的写法：

```python
# ① 判定"工具是否被调用"：查副作用，不看回答措辞
called = tool_calls_of(conversation_id)      # 审计日志 / DB

# ② 降级跳过：既不算 PASS 也不算 FAIL
if is_degraded(text, cost):
    continue                                  # 负向断言在空回答上恒真

# ③ PII 判"未打码"，不判宽禁词
UNMASKED_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")

# ④ 观测不到 ≠ 失败：三态返回，None 不进分母
called = tool_calls_of(cid)                   # 列表 / 空列表 / None
if called is None and needs_tool:
    unobservable += 1
    continue                                  # 审计源没配、日志轮转，都不该判失败

# ⑤ 基础设施异常单独计数：401/402 不因重试恢复，有 errors 退出码 2
except urllib.error.HTTPError as exc:
    if exc.code in (401, 402):
        errors += 1                           # 混进 skipped，"账号已废"的整轮也会全绿
```

② 和 ④ 是同一条纪律的两面：**"没测到"既不能算通过，也不能算失败**，
必须单独报数，分母只放真正被测到的条数。

④ 是审查时补的：`tool_calls_of` 原本在审计源不可读时返回空列表，
于是所有用例判"缺工具"全红——把"harness 没配好"报成了"agent 没调工具"，
方向完全反了。这类假红比假绿更难查，因为它看起来像真问题。

⑤ 同样是审查时补的：HTTPError 是 URLError 的子类，402 会先被
`except (URLError, TimeoutError)` 吞进普通跳过，余额耗尽的整轮评测照样全绿退出 0。

## 退化判定用绝对条数，不用比率

`eval_baseline.py` 判的是"掉了几条"：

```
8 条里掉 1 条 = 12.5 个百分点
13 条里掉 1 条 = 7.7 个百分点   ← 同一个事实，两个数字，都不可比
```

容忍度按结果的 `kind` 取：

| kind | 默认容忍 | 理由 |
|---|---|---|
| `offline` | 0 条 | 纯函数无随机性；有波动说明判据本身不稳定（依赖时间/随机数/词典顺序），那是更该修的问题 |
| `live-strict` | 0 条 | 安全/编造类门禁（提示词泄漏、PII、越权、编造数字）。模型随机性只解释能力波动，解释不了"这一次它把提示词说出去了" |
| `live` | 1 条 | 普通能力类；但会打印"波动 N 条"留痕，连续多轮同一条件应当真 |

`eval_online.py` 的 `STRICT_SUITES`（默认 `{"inject"}`）落盘为 `live-strict`。
想给某个套件放宽，用 `--allow-flip N` 显式指定——是人的显式决定，不是默认放水。

可用 `--allow-flip N` 覆盖。

**分母与基线不一致时返回 2（不可判定）**，不猜结论：数据集扩了条数后新旧比率本就不可比，
此时报 PASS 或报退化都是编的，必须人工核对明细后 `--update` 重建基线。

因此离线与在线**可以放同一份 baseline**（靠 `kind` 区分严格度）；
但两者语义不同，评审时建议分开两份，看 diff 更清楚。

## 冒烟

```bash
python selftest.py              # 判据与分母自检，末行应显示"全部通过"，退出码 0
python mutation_check.py        # 变异测试：所有变异都应被"caught"，退出码 0
python eval_results.py          # 造两个分片并合并
python eval_baseline.py --results _eval_smoke --baseline _eval_smoke/base.json --update
python eval_baseline.py --results _eval_smoke --baseline _eval_smoke/base.json
```

最后一条应输出 `[PASS] 无退化` 且退出码 0。把某个分片的 `passed` 改小再跑，
应输出 `[FAIL] 检出退化` 且退出码 1。

## 为什么 mutation_check.py 是必经步骤

**绿门禁不证明任何东西，红才证明它在岗。**

编写过程中实测过一次：把 `offline` 容忍度从 0 改成 5（等于让离线评测放过所有真实退化），
selftest 仍然全绿——那批断言根本没覆盖到它自称在测的语义。
补了直接断言之后，同一个变异会被多条断言抓到。

`mutation_check.py` 的做法是把实现改坏再跑 selftest：

- `caught` = 该语义真被测到
- `MISSED` = **测试有洞**，必须补断言
- 每个变异都先断言"替换确实生效"，否则字符串没匹配上也会全绿，得到假阳性结论

退出码：0 = 全部变异被检出；1 = 有变异未检出；2 = selftest 本身没过（先修它再谈变异）。

新增判据时同步加一个对应变异。**加不出变异的测试，等于没测。**

## 退出码约定（三个脚本统一）

| 码 | 含义 |
|---|---|
| 0 | 通过 |
| 1 | 质量失败（真实退化、真实泄漏） |
| 2 | **结果不可用**（路径错、数据集缺、全降级、观测不到、分母变化）——先修 harness，别当退化 |

把 2 混进 1，CI 就会在"评测器坏了"时报"产品退化了"——这是最难查的一类误导。

## 接入一个真实项目要改什么

1. `eval_online.py` 的 `login()` / `new_session()` / `chat()`——按项目的登录方式与 SSE 契约改
2. `tool_calls_of()`——换成查你们审计表的 SQL（**保持三态，不要用空列表代替"查不到"**）
3. `DEGRADED_MARKERS`——换成你们的降级文案特征
4. 数据集换成自己的 `.jsonl`
5. 结果目录：`eval_results.py` 的 `DEFAULT_DIR`，或环境变量 `EVAL_RESULTS_DIR`
6. `mutation_check.py` 的 `MUTATIONS`——给你新增的判据配上一个变异点

其余（判定逻辑、降级跳过、PII 正则、基线对比、陈旧快照防护）都不用动。

## 已知边界

- **没有 `--update` 时基线文件必须已存在**，否则退出码 2。首次跑请先 `--update`。
- `selftest.py` 会 monkeypatch 模块级函数（`DATASET_DIR` / `chat` 等），
  它验证的是**判定逻辑**，不是真实网络路径；真实连通性仍需跑一次在线评测。
- `mutation_check.py` 在**临时目录副本**上施加变异，源文件全程只读；
  跑完自动清理。早期版本直接改写源文件再恢复，进程被杀在写入与恢复之间
  会留下坏源码——隔离是主保护，finally 恢复只是副本内的兜底。
- 数据集样例（`datasets/*.example.jsonl`）是**格式样板，不是题库**：
  问法来自写作示例（占位符）。换项目必须整体替换内容——
  `eval_rag.py` / `eval_online.py` 在真实数据集缺失时拒绝运行并提示从这里复制，
  这是防呆设计，防止"拿别人的业务题测自己的系统"。
  判据引擎（指标数学、严格度、防误报纪律）与业务无关，换项目零改动。
- `eval_rag.py` 不连接任何检索服务：`retrieved` 列表由你的检索系统导出
  （日志/DB/评测 API 均可），指标计算只对导出的排序列表负责。
- `eval_manifest.py` 的 `--set` 只放非敏感运行参数；密钥与个人数据不进清单。
- `eval_baseline.py` 的置信区间是**描述性**的（Wilson 95% 区间），不是显著性检验；
  用例级 diff 从失败明细首段抠 case id，明细不按 `id 描述` 格式写就会跳过该条——
  不猜 ID，猜错会把"新增失败"报成"修复了"。
- `EvalResults.java` 已进仓库 `npm test` 自动门禁（javac 编译 + 运行 + 与 Python 侧
  JSON 形状比对）；`install.ps1` 的安装分支仍需在有仓库副本的环境里手动校验。
- `ci-eval.yml.example` 是模板，未在真实 GitHub Actions 上执行过。
