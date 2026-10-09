# dagcheck-plan

在执行 CI 或批处理流水线之前验证依赖图、查看关键路径，并模拟有限工作槽位的调度。
本工具不会执行任何任务。支持 Python 3.10+，运行时仅使用标准库，采用 MIT 许可证。

[English](../README.md) · [Русский](README.ru.md) · [Deutsch](README.de.md)

## 快速开始

在仓库根目录运行：

```sh
python -m pip install .
dagcheck-plan analyze examples/build.json --workers 2 --budget 8
python -m dagcheck_plan analyze examples/build.json --workers 2 --format json
python -m unittest discover -s tests -v
```

示例的关键路径为 `fetch -> test -> package`，无限并发工期和两槽位模拟工期均为 8。
所有时长使用同一个自选单位（例如秒或分钟）。

## 输入

```json
{"tasks":[{"id":"fetch","duration":2},{"id":"test","duration":5,"needs":["fetch"]}]}
```

根对象只能包含 `tasks` 数组。每个任务必须包含 `id` 和 `duration`，可选的 `needs`
默认为空数组。拒绝未知字段。ID 必须唯一、非空、区分大小写，且无首尾空白。ID 最多 256 个字符，拒绝 Unicode C 类（控制、格式、代理、私用和未分配字符）。
依赖必须为不重复且已存在的 ID。时长必须是有限的非负 JSON 数字，布尔值无效。
空图和零时长合法。重复 JSON 键、重复依赖、未知依赖、自依赖和环均报错。
环错误给出实际有向环，而不是仅列出被阻塞的下游任务。文件使用 UTF-8，`-` 表示标准输入。

## 结果与预算

- `topological_order`：每次选择可用 ID 中字典序最小者。
- `critical_path`：一条最长的连通源到汇路径；相同时取 ID 序列字典序最小者。
  这不是所有关键节点的集合。
- `timings`：无限容量下的最早/最晚开始与完成时间以及余量。
  不连通分量共享整个项目的完成时间来计算最晚时间。
- `unlimited_worker_makespan`：关键路径长度，也是有限并发工期的下界。
- `worker_lower_bound`：上述长度与总工作量除以槽位数两者的最大值。
- `schedule`：相同槽位、不可抢占的贪心调度。就绪任务按剩余关键路径长度降序、
  ID 字典序升序排列。先处理当前时刻的全部完成事件，再分配任务。
  零时长任务立即完成，其依赖后继可参与下一次分配。优先使用编号最小的空闲槽位。
- `heuristic_makespan`：本次可行调度的工期，不保证有限槽位下全局最优。
  超预算不等于证明不存在满足预算的调度。

`--workers` 默认为 **1**。`--budget` 始终约束模拟工期，不约束下界；等于预算视为通过。
未指定预算时，`within_budget` 为 JSON null。退出码：0 表示有效且满足预算（或无预算），
1 表示有效但模拟工期超预算，2 表示输入/参数错误或文件不可读。
报告写入标准输出，诊断写入标准错误。

内部将解析后数字的十进制表示转为精确有理数，因此 0.1 与 0.2 相加可满足 0.3 的预算。
非整数 JSON 输入首先经过 Python 浮点解析，不能保留任意精度小数。
非零 JSON 数字和命令行预算若下溢为零（如 `1e-400` 或 `-1e-400`），会作为无效输入拒绝，而不会被当作零处理。
精确的零和可表示的次正规数仍可接受。
非整数输出舍入为有限浮点数，整数输出精确；预算判断在输出舍入之前进行。

## Python API

```python
from dagcheck_plan import loads, plan, PlanError
report = plan(loads('{"tasks":[{"id":"lint","duration":3}]}'), workers=2, budget=4)
assert report["within_budget"] is True
```

`plan` 接受字典且不修改输入。`loads` 严格解析 JSON。无效输入抛出 `PlanError`
（`ValueError` 子类）。任务和依赖的输入顺序不会影响结果。

## 范围、开发与许可证

本工具仅分析估计时长，不运行命令、不读取 CI 密钥，也不模拟启动开销、缓存、重试或资源类别。
它不是优化器或安全沙箱，限制为 1,000,000 个输入字符、10,000 个任务和 100,000 条依赖边；字典 API 同样受任务/边限制。
超大输入的有理数计算可能昂贵，请仅使用可信项目配置。这些限制不是安全沙箱。
NetworkX 提供通用图算法，PyGraphviz 提供 Graphviz 集成；本项目专注于无需执行的预算检查 CLI。

测试覆盖模式验证、真实环、长链、零时长、排列稳定性、同时完成、预算、CLI 和 100 个固定种子的随机 DAG。
CI 在 Python 3.10–3.13 上测试，并安装后运行命令行示例。
图比较、资源类别容量和 GitHub Actions 适配器仅为后续方向，尚未实现。
贡献时请补充回归测试并更新四种语言文档，参见 [贡献指南](../CONTRIBUTING.md)。
采用 [MIT](../LICENSE) 许可证。
