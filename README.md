# 建筑垃圾运输优化平台

源头识别、接收匹配与车辆协同调度的建筑垃圾运输优化成果仓库。本仓库同时是一个**可直接部署到 GitHub Pages 的静态站点**。

## 在线预览

部署到 GitHub Pages 后：

- 首页（成果索引）：`https://<用户名>.github.io/<仓库名>/`
- 动态调度 Demo：`https://<用户名>.github.io/<仓库名>/demo.html`

## 目录结构

```
.
├─ index.html                       # 成果索引落地页（GitHub Pages 首页）
├─ demo.html                        # 交互式调度 Demo（单文件、无外部依赖）
├─ assets/                          # 方案、调研报告、对照表、汇报 PPT、架构图
├─ source/                          # 算法参考实现（Python）
├─ output/                          # 求解输出（结果 JSON / 调度 CSV / 联单 CSV）
├─ .github/workflows/pages.yml      # GitHub Pages 自动部署工作流
└─ .nojekyll                        # 关闭 Jekyll 处理
```

## 核心思路

先在源头确认材料与接收条件，再联合决定去向、车辆与时间，避免车开到门口才发现收不了。

1. **源头识别与分诊**：识别材质标签与置信度，低置信度或异常订单自动复核，且仍保证排入最终计划。
2. **接收匹配**：材质须落在设施接收目录内，类别须允许该类设施，泥浆强制先进预处理站。
3. **联合调度**：选车辆、选去向、排装卸顺序、定到场时刻，并计入路况与处理难度。
4. **前瞻合并**：估算当前任务完成后车辆可用时刻对后续任务花费的影响，综合评价后再合并。

目标函数：`综合成本 = 行驶 + 等待 + 处置 + 违约`。

## 效果对比（示例算例）

| 指标 | 点对点直送 | 算法优化后 | 变化 |
|---|---|---|---|
| 趟次 | 12 | 8 | −4 趟 |
| 总里程 | 1367.6 km | 1047.9 km | −23.4% |
| 综合成本 | 9153 元 | 7095 元 | −22.5% |
| 碳排 | 1230.9 kg | 943.1 kg | −23.4% |

> 数据为演示算例，实际参数需按当地台账标定。

## 运行参考实现

```bash
cd source
python srs_main.py
```

输出：`srs_result.json`、`srs_schedule.csv`、`srs_manifests.csv`。

## 部署到 GitHub Pages

1. 在 GitHub 新建仓库，把本目录推送上去：

```bash
git init
git add .
git commit -m "建筑垃圾运输优化平台"
git branch -M main
git remote add origin https://github.com/<用户名>/<仓库名>.git
git push -u origin main
```

2. 进入仓库 **Settings → Pages**，把 **Source** 设为 **GitHub Actions**。
3. 推送后 `.github/workflows/pages.yml` 会自动构建并发布，稍等片刻即可通过 Pages 链接访问。

> 备选方式：若不想用 Actions，也可在 **Settings → Pages** 选择 **Deploy from a branch**，分支选 `main`、目录选 `/ (root)`。

## 说明

- `demo.html` 为完全自包含单文件（地图边界、样式与算法逻辑全部内联），无第三方依赖，可直接静态托管。
- 里程单价、等待费率、处置费与碳因子均为算例参数，落地前须用当地实际台账标定。
