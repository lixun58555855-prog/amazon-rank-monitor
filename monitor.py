import json
import os
import re
import sys
import time
import urllib.parse
from playwright.sync_api import sync_playwright
from amazoncaptcha import AmazonCaptcha
import requests

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if not os.path.exists(config_path):
        print(f"❌ 找不到配置文件: {config_path}")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def handle_captcha_if_needed(page, max_retries=3):
    """检测并使用 amazoncaptcha 自动破解亚马逊 Robot Check 验证码"""
    for attempt in range(1, max_retries + 1):
        title = page.title()
        captcha_form = page.query_selector('form[action*="validateCaptcha"]')
        captcha_input = page.query_selector('input#captchacharacters')
        is_robot_check = "Robot Check" in title or "CAPTCHA" in title.upper()
        
        if not (captcha_form or captcha_input or is_robot_check):
            return True  # 没有验证码，安全通过

        input_elem = captcha_input or page.query_selector('input[type="text"]')
        if not input_elem:
            return True

        print(f"⚠️ [尝试 {attempt}/{max_retries}] 命中亚马逊验证码(Robot Check: {title})，正在自动破解...")
        
        img_element = page.query_selector('div.a-box-inner img') or page.query_selector('form img') or page.query_selector('img[src*="captcha"]')
        if not img_element:
            print("❌ 未能定位验证码图片元素")
            return False

        img_url = img_element.get_attribute('src')
        if not img_url:
            print("❌ 验证码图片链接为空")
            return False

        solution = AmazonCaptcha.fromlink(img_url).solve()
        print(f"💡 验证码识别结果: {solution}")

        if not solution or solution.strip() == "" or solution == "Not solved":
            print("❌ 验证码识别失败，重试中...")
            page.reload()
            page.wait_for_timeout(2000)
            continue

        input_elem.fill(solution)
        
        submit_btn = page.query_selector('button[type="submit"]') or page.query_selector('button.a-button-text')
        if submit_btn:
            submit_btn.click()
        else:
            page.keyboard.press('Enter')

        page.wait_for_load_state('domcontentloaded')
        page.wait_for_timeout(3000)

    if "Robot Check" in page.title() or page.query_selector('input#captchacharacters'):
        print("❌ 连续破解验证码失败，页面仍处于拦截状态！")
        return False
    
    print("✅ 验证码破盾成功，已进入页面！")
    return True

def set_delivery_zip(page, zip_code):
    """尝试设置配送邮编（如 90001）"""
    try:
        nav_global_location = page.query_selector('#nav-global-location-slot')
        if not nav_global_location:
            return
        
        current_text = nav_global_location.inner_text()
        if zip_code in current_text:
            print(f"📍 邮编已生效为: {zip_code}")
            return

        print(f"🔧 尝试切换配送地址邮编为: {zip_code} ...")
        page.click('#nav-global-location-slot')
        page.wait_for_selector('#GLUXZipUpdateInput', timeout=5000)
        page.fill('#GLUXZipUpdateInput', zip_code)
        page.click('#GLUXZipUpdate')
        page.wait_for_timeout(1000)
        
        # 关闭弹窗或刷新
        done_btn = page.query_selector('button[name="glowDoneButton"]') or page.query_selector('.a-popover-footer button')
        if done_btn:
            done_btn.click()
        page.wait_for_timeout(2000)
        print("📍 邮编设置指令已提交")
    except Exception as e:
        print(f"ℹ️ 邮编设置跳过或不适用: {e}")

def parse_search_page(page, target_asins, page_num):
    """解析当前搜索页，识别广告位(Sponsored)与自然位(Organic)"""
    results = []
    
    # 打印页面标题用于诊断
    try:
        print(f"🔍 [诊断] 页面标题: {page.title()} | 当前URL: {page.url}")
    except Exception:
        pass

    # 等待搜索结果列表加载
    items = page.query_selector_all('div[data-component-type="s-search-result"]')
    if not items:
        # 兼容备用选择器
        items = page.query_selector_all('div.s-result-item[data-asin]')

    if not items:
        # 如果还是没有，检查是否被阻拦或页面结构有变
        body_text = page.inner_text('body') if page.query_selector('body') else ""
        snippet = body_text.replace('\n', ' ')[:200]
        print(f"⚠️ [诊断] 未找到商品卡片，页面摘要: {snippet}")

    print(f"🔍 第 {page_num} 页共解析到 {len(items)} 个商品卡片")

    page_organic_idx = 0
    page_sponsored_idx = 0

    for item in items:
        asin = item.get_attribute('data-asin')
        if not asin or asin.strip() == "":
            continue

        # 判断是否带有 Sponsored 标识
        # 亚马逊通常会在卡片内标注 "Sponsored"、"Sponsored Ad" 或包含特定类
        item_text = item.inner_text()
        is_sponsored = False
        
        if "Sponsored" in item_text or "赞助商" in item_text:
            is_sponsored = True
        elif item.query_selector('.s-sponsored-label-info-icon') or item.query_selector('span:has-text("Sponsored")'):
            is_sponsored = True

        if is_sponsored:
            page_sponsored_idx += 1
            current_type = "Sponsored (广告位)"
            current_rank = page_sponsored_idx
        else:
            page_organic_idx += 1
            current_type = "Organic (自然位)"
            current_rank = page_organic_idx

        # 如果属于我们要监控的目标 ASIN
        if asin in target_asins:
            # 提取简短标题
            title_elem = item.query_selector('h2 a span') or item.query_selector('h2')
            title = title_elem.inner_text().strip() if title_elem else "N/A"
            if len(title) > 35:
                title = title[:35] + "..."

            # 提取价格
            price_elem = item.query_selector('span.a-price span.a-offscreen')
            price = price_elem.inner_text().strip() if price_elem else "N/A"

            results.append({
                "asin": asin,
                "title": title,
                "price": price,
                "page": page_num,
                "type": current_type,
                "rank_in_page": current_rank
            })

    return results

def run_monitor():
    config = load_config()
    marketplace = config.get("marketplace", "https://www.amazon.com").rstrip("/")
    max_pages = config.get("max_pages", 2)
    zip_code = config.get("zip_code", "90001")
    targets = config.get("targets", [])

    all_records = []

    with sync_playwright() as p:
        # 启动 Chromium
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-infobars',
            ]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-US",
            viewport={"width": 1920, "height": 1080},
            extra_http_headers={
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "accept-language": "en-US,en;q=0.9",
                "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "upgrade-insecure-requests": "1",
            }
        )

        # 抹除 WebDriver 指纹
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        page = context.new_page()

        # 访问主页初始化 Session
        print(f"🌐 正在连接亚马逊: {marketplace} ...")
        try:
            page.goto(marketplace, wait_until="domcontentloaded", timeout=30000)
            handle_captcha_if_needed(page)
            if zip_code:
                set_delivery_zip(page, zip_code)
        except Exception as e:
            print(f"⚠️ 访问首页异常，继续执行搜索: {e}")

        # 逐个关键词监控
        for target in targets:
            keyword = target["keyword"]
            target_asins = set(target["asins"])
            note = target.get("note", "")
            print(f"\n==================================================")
            print(f"🎯 正在监控关键词: 【{keyword}】 (关注 ASIN: {target['asins']})")
            print(f"==================================================")

            found_items = []

            for page_num in range(1, max_pages + 1):
                encoded_kw = urllib.parse.quote_plus(keyword)
                search_url = f"{marketplace}/s?k={encoded_kw}&page={page_num}"
                
                print(f"📄 正在检索第 {page_num} 页 ...")
                
                if page_num == 1:
                    # 优先通过首页搜索栏模拟真实用户搜索，规避 503 拦截
                    search_box = page.query_selector('input#twotabsearchtextbox')
                    if search_box:
                        search_box.fill(keyword)
                        search_box.press('Enter')
                        page.wait_for_load_state('domcontentloaded')
                    else:
                        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                else:
                    # 第 2 页及之后，优先模拟点击“Next”按钮
                    next_btn = page.query_selector('a.s-pagination-next') or page.query_selector('a:has-text("Next")')
                    if next_btn:
                        next_btn.click()
                        page.wait_for_load_state('domcontentloaded')
                    else:
                        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

                # 破盾处理
                handle_captcha_if_needed(page)

                # 如果遭遇 503 "Sorry! Something went wrong!"，刷新重试
                if "Sorry! Something went wrong!" in page.title():
                    print("⚠️ 命中亚马逊 503 拦截，正在回退刷新...")
                    page.wait_for_timeout(2000)
                    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    handle_captcha_if_needed(page)

                # 模拟滚动以触发懒加载
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(1500)

                # 解析
                matches = parse_search_page(page, target_asins, page_num)
                for m in matches:
                    m["keyword"] = keyword
                    m["note"] = note
                    found_items.append(m)
                    print(f"  👉 命中目标! ASIN: {m['asin']} | {m['type']} #第{m['rank_in_page']}位 (第{page_num}页) | 价格: {m['price']}")

                time.sleep(2)  # 礼貌间隔

            # 如果某些目标 ASIN 在前 N 页没有找到
            found_asins = {m["asin"] for m in found_items}
            for missed_asin in target_asins - found_asins:
                miss_record = {
                    "keyword": keyword,
                    "asin": missed_asin,
                    "title": "未进入监控范围",
                    "price": "-",
                    "page": f"> {max_pages}",
                    "type": "未上榜 / 掉出范围",
                    "rank_in_page": "-",
                    "note": note
                }
                found_items.append(miss_record)
                print(f"  ❌ 目标 ASIN {missed_asin} 未在前 {max_pages} 页找到！")

            all_records.extend(found_items)

        browser.close()

    # 导出报告与展示
    generate_summary_reports(all_records)

def generate_summary_reports(records):
    """生成本地 JSON 以及 GitHub Actions Step Summary 表格"""
    output_file = "rank_report.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"\n📁 详细监控数据已保存至: {output_file}")

    # 生成 Markdown 表格
    headers = ["关键词", "目标 ASIN", "排名类型", "所在页码", "页内位次", "价格", "备注"]
    rows = []
    for r in records:
        rows.append([
            r["keyword"],
            f"`{r['asin']}`",
            r["type"],
            f"第 {r['page']} 页" if str(r['page']).isdigit() else str(r['page']),
            f"#{r['rank_in_page']}" if str(r['rank_in_page']).isdigit() else str(r['rank_in_page']),
            r.get("price", "-"),
            r.get("note", "")
        ])

    md_table = "| " + " | ".join(headers) + " |\n"
    md_table += "| " + " | ".join(["---"] * len(headers)) + " |\n"
    for row in rows:
        md_table += "| " + " | ".join(row) + " |\n"

    print("\n" + md_table)

    # 如果运行在 GitHub Actions 环境中，写入 GITHUB_STEP_SUMMARY
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("## 🚀 亚马逊 ASIN 关键词排名监控快照\n\n")
            f.write(f"> 运行时间: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n\n")
            f.write(md_table)
            f.write("\n\n---\n*监控引擎: Playwright + amazoncaptcha (零代理方案)*\n")

if __name__ == "__main__":
    run_monitor()
