# Amazon ASIN 关键词排名监控器（免代理 + 自动打码）

基于 **GitHub Actions + Playwright + amazoncaptcha** 的全自动亚马逊自然位与广告位排名监控系统。

## ✨ 特性

- 🆓 **完全零成本**：无需购买昂贵的住宅代理，无需付费打码平台。
- 🛡️ **本地毫秒级破盾**：集成基于亚马逊验证码字体训练的本地识别库 `amazoncaptcha`，命中 Robot Check 验证码时秒级自动填写破盾（准确率 99%）。
- 🎯 **广告位与自然位分离**：精确区分商品推广广告（Sponsored Products）与纯自然坑位（Organic Rank）。
- 📍 **配送地邮编支持**：支持指定美国邮编（如 `90001`），避免因地域不同导致的搜索排名失真。
- 📊 **GitHub 自动化看板**：每次运行自动将排名快照输出为 GitHub Step Summary 汇总表格，并打包下载 JSON 数据。

## 📁 目录结构

```text
├── .github/workflows/
│   └── rank_monitor.yml   # GitHub Actions 定时流水线配置
├── config.json            # 目标关键词、ASIN 及邮编配置
├── monitor.py             # 核心监控与破盾爬虫脚本
├── requirements.txt       # Python 依赖项
└── README.md
```

## ⚙️ 配置说明 (`config.json`)

在 `config.json` 中配置你需要监控的关键词与 ASIN 列表：

```json
{
  "marketplace": "https://www.amazon.com",
  "zip_code": "90001",
  "max_pages": 2,
  "targets": [
    {
      "keyword": "wireless earbuds",
      "asins": ["B09X1KZZQ5", "B0B94ZWS5T"],
      "note": "主力耳机与竞品监控"
    }
  ]
}
```

* `marketplace`: 站点域名（默认为美站 `https://www.amazon.com`）。
* `zip_code`: 配送地址邮编（默认加州 `90001`）。
* `max_pages`: 每次关键词扫描前几页（建议 2~3 页，平衡运行时间）。
* `targets`: 监控任务数组，一个关键词下可同时追踪多个 ASIN（自己的主推品与竞品）。

## 🚀 部署到 GitHub 使用

1. 在 GitHub 上新建一个仓库（建议设为 **Private 私有仓库**）。
2. 将本项目所有代码上传至该仓库：
   ```bash
   git init
   git add .
   git commit -m "feat: init amazon rank monitor"
   git remote add origin <你的仓库地址>
   git push -u origin main
   ```
3. 进入 GitHub 仓库页面：
   * 点击顶部的 **Actions** 标签。
   * 在左侧找到 **Amazon ASIN Rank Monitor** 流水线。
   * 点击 **Run workflow** 即可手动运行一次测试；之后它会按照 cron 定时任务每 6 小时自动执行一次。
4. 运行完成后，在当次 Action 详情页下方可直接查看漂亮的**排名汇总快照表格**！
