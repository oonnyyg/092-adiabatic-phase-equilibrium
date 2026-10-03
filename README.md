# phase_balance — 绝热混合相平衡计算

计算多种材料在绝热容器中仅交换热量（忽略反应、蒸发与容器吸热，材料互不
溶解）后的共同平衡温度与各材料液相比例，并核对每种材料的吸放热是否闭
合。仅使用 Python 标准库。

## 用法

```
python -m phase_balance 输入.json --out 输出目录
```

- 入口先校验**所有**实验；任一实验非法则整批失败（退出码 2），不生成
  任何报告。
- 校验通过后在输出目录生成：
  - `materials.csv`：每种材料一行的结果表；
  - `summary.json`：每个实验的平衡温度、初末总焓与残差汇总。

## 输入格式

```json
{
  "experiments": [
    {
      "id": "mix-1",
      "materials": [
        {
          "id": "water",
          "mass": 1.0,
          "cp_solid": 2100.0,
          "cp_liquid": 4180.0,
          "melt_point": 0.0,
          "latent_heat": 334000.0,
          "initial_temp": 25.0
        },
        {
          "id": "wax",
          "mass": 0.5,
          "cp_solid": 2000.0,
          "cp_liquid": 2500.0,
          "melt_point": 45.0,
          "latent_heat": 200000.0,
          "initial_temp": 45.0,
          "initial_liquid_fraction": 0.0
        }
      ]
    }
  ]
}
```

## 单位与字段约定

- 统一单位：质量 kg、能量 J、温度 摄氏度；比热为 J/(kg·°C)，潜热为
  J/kg。
- 所有数值必须有限；`mass`、`cp_solid`、`cp_liquid`、`latent_heat`
  必须为正。
- 实验编号、同一实验内的材料编号必须唯一；同一实验内各材料熔点必须
  互不相同。
- 每个实验至少一种材料。

## 焓模型与相变边界

- 每种材料以**熔点处全固态**为零焓点：
  - `T < Tm`：`h = cp_solid * (T - Tm)`
  - `T > Tm`：`h = latent_heat + cp_liquid * (T - Tm)`
  - `T == Tm`：`h = latent_heat * f`（`f` 为液相比例）
  - 总焓为 `mass * h`。
- 初温恰等于熔点时**必须**给出 `[0, 1]` 内的
  `initial_liquid_fraction`；其他温度不允许指定该字段。
- 求解按总初焓守恒进行：总焓对温度单调分段线性，因此平衡温度唯一。
  若总焓落在某材料的潜热平台上，温度停在该熔点并解出部分液化比例，
  不会跨过相变区直接平均温度；其余材料按最终温度判定全固或全液。

## 输出与核对

- 每种材料报告初末焓与净吸热 `net_heat_J`（末焓 − 初焓）。
- `summary.json` 中 `enthalpy_residual_J` 为末总焓与初总焓之差，应接
  近 0；各材料净吸热之和同样闭合。
- 平衡温度绝对误差不超过 1e-7 °C，液相比例误差不超过 1e-8。

## 测试

```
python -m unittest discover -s tests -v
```
