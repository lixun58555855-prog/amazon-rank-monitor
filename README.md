# Amazon ASIN 关键词排名跨区域监控系统

基于 **GitHub Actions + Playwright + amazoncaptcha** 的全自动亚马逊多站点、热门城市邮编切换、自然位与广告位排名监控系统。

## ✨ 核心亮点

- 🌐 **多站点支持**：可灵活配置美国站 (`amazon.com`)、英国站 (`amazon.co.uk`)、德国站 (`amazon.de`) 等多个国家。
- 📍 **热门城市分仓邮编切换**：自动模拟点击配送定位，切换目标代表性城市邮编（如美西 `90001`、美东 `10001`、美中 `60601`），真实反映区域分仓库存与本地化广告展示。
- 📊 **横向对比透视看板**：自动在 GitHub Actions 汇总页生成 **Cross-City Comparison** 矩阵表格，一眼看清同一 ASIN 在各个大城市的广告位与自然位波动。
- 🛡️ **本地毫秒级破盾**：集成 `amazoncaptcha`，遭遇 Robot Check 验证码时纯本地 OCR 自动填码破盾（准确率 99%），无需购买付费代理池。
- 🎯 **广告位与自然位精准分离**：独立统计商品推广广告位（Ad）与纯自然坑位（Nat）。

## ⚙️ 配置指南 (`config.json`)

在 `config.json` 中配置站点与城市：

```json
{
  "marketplaces": [
    {
      "site": "US",
      "name": "美国站",
      "base_url": "https://www.amazon.com",
      "locations": [
        { "city": "Los Angeles (美西)", "zip": "90001" },
        { "city": "New York (美东)", "zip": "10001" },
        { "city": "Chicago (美中)", "zip": "60601" }
      ],
      "max_pages": 2,
      "targets": [
        {
          "keyword": "wireless earbuds",
          "asins": ["B09X1KZZQ5", "B0B94ZWS5T"],
          "note": "主力耳机监控"
        }
      ]
    }
  ]
}
```

## 📊 看板呈现示例

运行后，GitHub Actions 的 Step Summary 会渲染出如下**城市横向透视对比表**：

| 站点 | 关键词 | 目标 ASIN | Chicago (60601) | Los Angeles (90001) | New York (10001) |
| --- | --- | --- | --- | --- | --- |
| 美国站 | wireless earbuds | `B09X1KZZQ5` | Nat P1#3 / Ad P1#1 | Nat P1#5 | Nat P1#12 |
| 美国站 | wireless earbuds | `B0B94ZWS5T` | ❌ 未上榜 | Ad P1#2 | ❌ 未上榜 |

> **图例说明**：
> * `Ad P1#1`: 第 1 页第 1 个 Sponsored 广告位
> * `Nat P1#3`: 第 1 页第 3 个 Organic 自然位
