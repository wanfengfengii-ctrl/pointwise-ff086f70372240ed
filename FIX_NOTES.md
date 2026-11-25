# 复盘链修复记录

## 症状

- `python3 -B check_project.py`：30 项中 8 项失败。
- `python3 -B -m review.cli demo`：签出 `概率 1/2、平均 0 码`，期望 `1/4、1/3`。

## 根因

1. `issue/freeze.py` 的 `project_revision`
   把 `silent` 边投影成 `end` 边，静默推进被当成终止。结果是：
   - 静默边后的整条后缀被截断；
   - 含静默边的规程，其完整公开记录质量被错误重分配；
   - 乙站本应经静默进入采样状态的质量被直接并入空记录。
   这违反“发行件须保全所选修订对每条完整公开记录赋予的概率”。

2. `review/agreement.py` 的 `_completed_records`
   用深度优先枚举记录，且以 `state not in prior_states` 剪枝，静默与公开回边都被禁止重访。
   因此“任意有限次循环及同码分支”全被丢弃，只剩简单路径，样例因此报 `1/2、0`。

## 修复

- `project_revision`：保留 `silent` 边的类型与后继，只把站内状态名映射为局部编号；仅 `end` 边无后继。
- `agreement._completed_records` 替换为精确的嵌入式链求解：
  1. 以 `(I - Q)` 精确求逆做静默闭包（`Q` 为静默子随机矩阵；每个可达状态均有正概率结束，故瞬态可逆）；
  2. 得到可观测跳跃链：每步消耗一个公开码或终止；
  3. 在左右状态的笛卡尔积上建立 `(I - M)` 有理线性系统，先求一致概率，再用同一分解求条件长度质量；
  4. 同码多边在闭包中合并且全部计入；循环质量由矩阵求逆精确包含，不做任何截断或抽样；
  5. 只对一致事件取平均，概率为零时长度为 `None`。

全部计算使用 `Fraction` 与 `review.linear_system.RationalSystem`，不抽样、不浮点。

## 实测结果

```
$ python3 -B check_project.py
TEST SUMMARY total=37 failures=0 errors=0 ... result=PASS

$ python3 -B -m review.cli demo
"actual": {"mean_length": "1/3", "probability": "1/4"}   EXIT=0
```

`demo` 的 `actual == expected`，且历史复领的 `downstream_actual == downstream_expected`。

## 新增回归（`tests/test_regressions.py`）

- 静默边在发行投影后仍是 `silent` 且有后继；
- 甲乙两站发行件对每条完整公开记录的质量：
  甲 `()=3/4, (X)=1/8`，乙 `()=1/4, (X)=3/8`，`(X,X)=3/16 …` 逐项保持；
- 静默/公开自环的单状态规程自比：`1/3`、`1/3`（闭式）；
- 同件放左右两位置按独立运行：甲站 `7/12`、`1/21`（闭式）；
- 完全无共同码：概率 `0`、长度为 `null`；
- 发行件不含设备编号与站内状态名；
- `run_day_sample` 端到端签出 `1/4`、`1/3`，下游历史一致。

## 额外核验

对 120 组随机合法规程做了独立核验：发行投影逐条完整公开记录质量不变；
一致性概率与条件长度落在与独立枚举 + 精确尾部上界证明一致的范围内。

## 保留

- 原有 30 项测试全部保留并通过；`demo` 与 `check_project.py` 入口未改。
