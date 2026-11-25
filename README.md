# 海岚检测实验室规程复盘台账

使用 Python 3.11 标准库及 SQLite。站端规程员定版设备检修后的诊断规则，试验员录入已结束的试跑，中心质控员离线复盘两个指定规程，次班按报告号领取签存成果。

## 运行

```sh
python3 -B check_project.py
python3 -B -m review.cli demo
```

`check_project.py` 由控制台物化时提供。独立检出也可直接运行 `python3 -B -m unittest discover -s tests -t . -v`。演示用 `samples` 中的固定输入，经过定版、试跑、发行、补送、实收、关源核算、更正和重开。演示在隔离临时目录创建数据库并清理，输出含真实核算值和历史复领值的一行 JSON。

## 日常交班

1. 规程员从设备字典录入公开码及描述，并提交内部状态、初态和转移。
2. 站库只在完整校验通过后分配冻结修订号。后续纠正可沿用规程号，获得新的独立修订。
3. 试验员以修订号录入已结束的实跑。支持检查按原顺序消费报码，允许静默推进及同码分支，消费完仍须能合法结束。结构有效的规程外记录照常留档。
4. 站端对选定修订发行固定件。领取旧发行号取得原件字节。
5. 中心独立校验并实收。相同发站及发行号的原字节重送返回首次结果。同身份的其他合法件形成冲突登记。
6. 站库关闭后，中心按请求中的左右实收号选取原件，其他实收件不影响本次取证。
7. 核定两次独立运行产生相同完整记录的概率及相同时平均报码数，一起签存定稿、左右出处和回执。
8. 源站更正或中心重开后，换班人员按报告号读出已签内容。

## Python 接口

使用 `ledger.open_database(path)` 打开站库或中心库。站库依次初始化 `protocol.revisions.RevisionStore`、`runs.history.RunHistory`、`issue.register.IssueRegister(connection, site)`。中心库依次初始化 `intake.store.IntakeStore`、`review.store.ReportStore`。各 store 的 `initialize()` 只创建缺失的表或索引，保留用户修订和历史。连接的关闭由调用方负责。供业务写入口使用的连接应启用 SQLite 外键并处于事务之外。

| 入口 | 参数和返回 |
| --- | --- |
| `protocol.catalog.build_catalog` | 公开码到描述的映射，返回字典快照。空字典适用于无报码规程。 |
| `protocol.revisions.seal_revision` | `(revisions, protocol_id, catalog, graph, device_id=...)`，返回冻结修订号。`revisions.load(revision_id)` 读回该修订。 |
| `runs.import_run.record_run` | `(history, revision_id, codes)`，返回 `ObservedRun`。`codes` 是文本码的列表或元组。`history.read(run_id)` 及 `history.for_revision(revision_id)` 读回原报码及核查状态。 |
| `issue.freeze.issue_revision` | `(register, revision_id)`，返回 `IssuedEnvelope`，含 `issue_id`、`revision_id` 和 `raw`。 |
| `issue.retrieve.retrieve_piece` | `(register, issue_id)`，返回原发行件。 |
| `intake.receive.receive_piece` | `(intake, raw)`，返回 `AcceptedPiece`，含 `intake_id`、原外层及首执。 |
| `review.publish.review_pair` | `(reports, left_id, right_id)`，返回 `SignedReport`，含报告号、统计、左右父件及回执。两个位置可以取同一件，仍按独立运行计算。 |
| `review.history.read_report` | `(reports, report_id)`，返回当时签存的 `SignedReport`。 |

在 `protocol.transitions` 中以 `TransitionGraph(states, initial, transitions)` 建图。每条 `Transition(source, kind, weight, target=None, code=None)` 的概率用整数或 `Fraction`。站内状态名为非空文本。`silent` 有后继，`public` 同时带后继和公开码，`end` 无码也无后继。所有状态的行质量恰为一，只有严格正权边参与可达性和结束性检查。允许零权边、同码多边及不可达的合法行。字典描述、设备编号和现场原记录留在站库。

编号为正整数。未知修订、发行号、实跑号或报告号抛出 `KeyError`，按修订号查询实跑索引时无匹配返回空元组。结构或领域非法输入抛出 `ValueError`。中心错件请求抛出 `ValueError`。身份冲突抛出 `PieceConflict` 并保留首件首执。非法或损坏来件无成功实收，不生成成功回执。签存数据库错误由调用方得到，报告、父件和回执一同回滚，原实收件可重试。

## V1 固定件和计算口径

固定件为 UTF-8 JSON。外层键为 `version`、`site`、`issue_id`、`revision_id`、`body_sha256`、`body`，版本为整数 `1`。`body` 是正文 JSON 文本，`body_sha256` 是该文本 UTF-8 字节的 SHA-256 小写十六进制值。实收保存完整外层的首次原始字节。

正文键为 `initial`、`state_count`、`transitions`。局部状态从零开始连续编号。每条转移记录为 `[源,类型,后继,公开码,[分子,分母]]`，缺项用 `null`。分母须为正，整数对须约分。正文 JSON 按键排序、无附加空白、保留 Unicode，转移按源、类型、后继、码、分子、分母排序。结束边的后继排序值取 `-1`，无码的码排序值取空串。正文保留并列转移，不公开站内状态名。

统计的概率和条件长度在 Python 返回值中使用 `Fraction`，历史记录和演示用其精确字符串表示。长度单位为公开报码个数，静默和结束计零。共同结束的空记录纳入一致概率。只有两边完整结束且公开序列逐项相等才算一致。零一致概率的条件长度为 `None`，JSON 为 `null`。两边必然空记录时概率为一、长度为零。计算不抽样。

样例甲、乙共同空记录的质量为 `3/16`，非空共同质量从 `3/64` 起按 `1/4` 递减，合为 `1/16`。非空部分的长度质量为 `1/12`。因此应签概率 `1/4`、条件长度 `1/3`。原回归另核对同码分支、独立合规件、空记录和零一致、错件、重开历史及 SQLite 提交失败后的回滚与重试。
