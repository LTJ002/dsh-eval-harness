# dsh-eval-harness

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![dsh-plugin](https://img.shields.io/badge/dsh-plugin-8A2BE2)](https://github.com/topics/dsh-plugin)

面向 DeepSeek Harness（DSH）的 **Agent 应用开发评测工具**。核心不是跑分，而是**让每个数字都可复现、可比较、且不骗人**：判定依据必须来自外部事实（审计表、服务端结构化结果、确定性规则），判据必须双向（该答未答 / 不该答却答了），并且用变异测试证明评测器自己没坏。覆盖 RAG 检索、工具调用、提示词安全与多轮对话的评测设计。

> 文档与技能正文为中文；README 另提供[英文版](README.en.md)。

## 什么时候用

| 场景 | 用它做什么 |
|---|---|
| 为 LLM/Agent 应用建立质量度量 | 从零搭起"离线断言 + 在线真打模型 + 基线对比"三层评测 |
| 改完 RAG / 工具 / 提示词，要证明没退化 | 与基线按用例对比，掉条数就红，安全类零容忍 |
| 评测全绿，线上仍出问题 | 用四陷阱清单与根因分层逐项核对判据，找假绿 |
| 怀疑评测脚本在骗自己 | 跑 `mutation_check.py`：改坏实现看断言敢不敢红 |
| 数字"看起来对"但不敢信 | 五态结果契约 + 分母纪律 + 小样本标注，让每个数字可解释 |

## 安装

```sh
dsh plugin add https://github.com/LTJ002/dsh-eval-harness
```

技能会以 bundled provider 的形式出现在 `ctx.skills` 中（rank 600），会话内通过技能目录或 `@ai-eval-harness` 引用；无需复制到项目的 `.agents/skills`。

## 它是什么 / 不是什么

这是一个**技能包**：`skills/ai-eval-harness/SKILL.md` 是给模型读的方法论（判据设计、陷阱清单、基线纪律），`skills/ai-eval-harness/assets/` 是可直接运行/改写的评测实现（Python 标准库实现，JUnit 落盘器用 Java）。它不提供任何 UI 或会话命令——所有能力都通过技能正文与资产脚本体现。

## 适用范围：所有 agent 应用开发框架

本工具**框架无关**：不绑定、不内置、也不需要任何 agent 开发框架的 SDK。任何框架构建的 Agent 应用——LangChain、LangChain4j、Spring AI、AutoGen、CrewAI、Dify 等——只要满足两个前提，就能用同一套评测：

1. **对话可编程访问**——应用暴露可调用的对话接口（HTTP/SSE 均可；`eval_online.py` 用标准库 urllib 对接，`login()` / `chat()` 按你的项目契约改写）；
2. **副作用可查询**——工具调用、写操作等副作用留有可查询的记录（审计表、结构化日志或 DB）——判据从外部事实读取，不读模型的自我陈述。

前提与框架解耦，所以评测方法学（双向判据、分母纪律、基线对比、变异测试）跨框架通用；换框架只改适配层，不改判据。评测器集成层按项目语言选择：

- **Python 项目**：`assets/` 下脚本直接可用（仅标准库）；
- **Java/JUnit 项目**：用 `EvalResults.java` 产出与 Python 同形的 JSON 分片；
- **其他语言**：只要能写出约定 JSON 形状的结果分片，`eval_baseline.py` 就能消费（形状见 [assets/README.md](skills/ai-eval-harness/assets/README.md)）。

文档中提及 LangChain / LangChain4j 仅用于解释切片参数的计量单位语义，**不构成对任何具体框架的集成声明**。

## 资产一览

| 文件 | 用途 |
|---|---|
| `assets/eval_results.py` | 结果落盘（分片 + `kind` 字段，防并发覆盖） |
| `assets/eval_baseline.py` | 基线对比：按绝对条数判退化；offline / **live-strict** / live 三档严格度；分母变化不判定 |
| `assets/eval_online.py` | 在线评测骨架：`tool` / `inject` / `answer` 三套件，内置五条防误报纪律 |
| `assets/selftest.py` | 判据与分母纪律的回归自检（改任何脚本后必跑） |
| `assets/mutation_check.py` | 变异测试：把实现改坏，验证断言会翻红；在临时副本上施加变异 |
| `assets/EvalResults.java` | JUnit 场景的结果落盘，JSON 形状与 Python 版一致 |
| `assets/datasets/*.example.jsonl` | 数据集样例（换项目必须整体替换） |
| `assets/install.ps1` | 把 bundle 从仓库副本装到用户级 skill 根；`-VerifyOnly` 校验分叉 |

## 五条防误报纪律（`eval_online.py` 固化为可运行代码）

```python
# ① 工具是否被调用 → 查审计日志，不看回答措辞
called = tool_calls_of(conversation_id)

# ② 降级跳过：负向断言在空回答上恒真，不能算 PASS
if is_degraded(text, cost):
    continue

# ③ PII 判"未打码"，不判宽禁词
UNMASKED_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")

# ④ 观测不到 → None，不进分母也不判失败
called = tool_calls_of(cid)                   # 列表 / 空列表 / None
if called is None and needs_tool:
    unobservable += 1
    continue

# ⑤ 401/402 基础设施异常单独计 errors：不因重试恢复，退出码升 2
except urllib.error.HTTPError as exc:
    if exc.code in (401, 402):
        errors += 1
```

## 严格度三档

| kind | 默认容忍波动 | 理由 |
|---|---|---|
| `offline` | 0 条 | 纯函数无随机性，掉 1 条就是真掉了 |
| `live-strict` | 0 条 | 安全/编造类门禁（提示词泄漏、PII、越权）：随机性解释能力波动，解释不了泄漏 |
| `live` | 1 条 | 普通能力类；波动必须留痕 |

## 本地验证

```sh
npm test                                   # bundle 结构冒烟（node:test）
python skills/ai-eval-harness/assets/selftest.py          # 判据自检
python skills/ai-eval-harness/assets/mutation_check.py    # 变异测试
```

三项在本仓库发布前均验证通过（断言全过、24 个变异全部 caught；条数随技能演进变化，以本地运行输出为准）。

## 退出码约定

| 码 | 含义 |
|---|---|
| 0 | 通过 |
| 1 | 质量失败（真实退化、真实泄漏） |
| 2 | 结果不可用（路径错、数据集缺、全降级、观测不到、分母变化、401/402）——先修 harness，别当退化 |

## 已知边界

- `eval_online.py` 是**骨架**：`login()` / `chat()` / `tool_calls_of()` 需按你的项目契约改写；数据集样例来自摄影订单项目，换项目必须整体替换。
- 判定逻辑的回归自检 monkeypatch 模块级函数，验证的是判定纪律，不是真实网络路径。
- `EvalResults.java` 与 `install.ps1` 未在 CI 中自动验证；接入时请先跑一次冒烟。

## License

[MIT](LICENSE)
